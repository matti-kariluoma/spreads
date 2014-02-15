import json
import logging
import logging.handlers
import os
import random
import StringIO
import time
import zipfile

import jpegtran
import mock
import pytest
from multiprocessing.pool import ThreadPool


@pytest.yield_fixture
def app(config, mock_driver_mgr, mock_plugin_mgr, tmpdir):
    from spreadsplug.web import setup_app, app
    from spreads.plugin import set_default_config
    set_default_config(config)
    logger = logging.getLogger()
    config['loglevel'] = 'warning'

    logfile = tmpdir.join('logfile.txt')
    logfile.write('')
    file_handler = logging.handlers.RotatingFileHandler(
        filename=unicode(logfile), maxBytes=512*1024, backupCount=1)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(message)s [%(name)s] [%(levelname)s]"))
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    config['logfile'] = unicode(logfile)
    config['web']['mode'] = 'full'
    config['web']['database'] = unicode(tmpdir.join('test.db'))
    config['web']['project_dir'] = unicode(tmpdir)
    config['web']['debug'] = False
    config['web']['standalone_device'] = True
    setup_app(config)
    app.config['TESTING'] = True
    yield app


@pytest.yield_fixture
def client(app):
    yield app.test_client()


@pytest.yield_fixture
def mock_dbus(tmpdir):
    with mock.patch.multiple('dbus', SystemBus=mock.DEFAULT,
                             Interface=mock.DEFAULT) as values:
        stickdir = tmpdir.join('stick')
        stickdir.mkdir()
        mockdevs = [mock.Mock(), mock.Mock()]
        mockobj = mock.MagicMock()
        mockobj.get_dbus_method.return_value.return_value = unicode(stickdir)
        mockobj.EnumerateDevices.return_value = mockdevs
        mockobj.Get.side_effect = [True, 'usb', True]
        values['Interface'].return_value = mockobj
        yield mockobj


@pytest.fixture
def jsonworkflow():
    return json.dumps({
        'name': 'foobar'
    })


@pytest.yield_fixture
def worker():
    from spreadsplug.web.worker import ProcessingWorker
    worker = ProcessingWorker()
    worker.start()
    time.sleep(1)
    yield
    worker.stop()


def create_workflow(client, num_captures='random'):
    workflow = {
        'name': 'test{0}'.format(random.randint(0, 8192)),
    }
    data = json.loads(client.post('/workflow',
                      data=json.dumps(workflow)).data)
    if num_captures:
        client.post('/workflow/{0}/prepare_capture'.format(data['id']))
        for _ in xrange(random.randint(1, 16)
                        if num_captures == 'random' else num_captures):
            client.post('/workflow/{0}/capture'.format(data['id']))
        client.post('/workflow/{0}/finish_capture'.format(data['id']))
    return data['id']


def test_index(client):
    rv = client.get('/')
    assert "<title>spreads</title>" in rv.data
    assert "<script src=\"spreads.min.js\"></script>" in rv.data


def test_get_plugins_with_options(client):
    data = json.loads(client.get('/plugins').data)
    # TODO: Check the data some more
    assert len(data.keys()) == 4


def test_get_global_config(client):
    cfg = json.loads(client.get('/config').data)
    assert cfg['plugins'] == ['test_output', 'test_process', 'test_process2']
    assert cfg['driver'] == 'testdriver'
    assert cfg['web']['mode'] == 'full'


def test_create_workflow(client, jsonworkflow):
    data = json.loads(client.post('/workflow', data=jsonworkflow).data)
    workflow_id = data['id']
    data = json.loads(client.get('/workflow/{0}'.format(workflow_id)).data)
    assert data['name'] == 'foobar'
    assert data['id'] == 1


def test_list_workflows(client):
    for _ in xrange(5):
        create_workflow(client)
    data = json.loads(client.get('/workflow').data)
    assert isinstance(data, list)
    assert len(data) == 5
    assert 'config' in data[0]


def test_get_workflow(client):
    wfid = create_workflow(client)
    data = json.loads(client.get('/workflow/{0}'.format(wfid)).data)
    assert 'test_output' in data['config']['plugins']
    assert data['step'] == 'capture'
    assert data['capture_start'] < time.time()


def test_update_workflow(client):
    wfid = create_workflow(client)
    workflow = json.loads(client.get('/workflow/{0}'.format(wfid)).data)
    workflow['config']['foo'] = 'bar'
    data = json.loads(
        client.put('/workflow/{0}'.format(wfid), data=json.dumps(workflow))
        .data)
    assert data['config']['foo'] == 'bar'


def test_delete_workflow(client):
    wfid = create_workflow(client)
    client.delete('/workflow/{0}'.format(wfid))
    data = json.loads(client.get('/workflow').data)
    assert len(data) == 0


def test_poll_for_updates_workflow(client):
    wfid = create_workflow(client)
    pool = ThreadPool(processes=1)
    asyn_result = pool.apply_async(client.get, ('/poll', ))
    client.post('/workflow/{0}/prepare_capture'.format(wfid))
    client.post('/workflow/{0}/capture'.format(wfid))
    rv = asyn_result.get()
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert len(data['workflows']) == 1
    # TODO: Be more thorough


def test_poll_for_updates_errors(client):
    # TODO: Spin up background thread that GETs '/poll'
    # TODO: Provoke an error logentry on the server, verify that the thread
    #       finished
    wfid = create_workflow(client)
    pool = ThreadPool(processes=1)
    asyn_result = pool.apply_async(client.get, ('/poll', ))
    with mock.patch('spreadsplug.web.web.shutil.rmtree') as sp:
        sp.side_effect = OSError('foobar')
        client.delete('/workflow/{0}'.format(wfid))
    rv = asyn_result.get()
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert len(data['messages']) == 1
    # TODO: Be more thorough


def test_download_workflow(client):
    wfid = create_workflow(client, 10)
    data = client.get('/workflow/{0}/download'.format(wfid)).data
    zfile = zipfile.ZipFile(StringIO.StringIO(data))
    assert len([x for x in zfile.namelist()
                if '/raw/' in x and x.endswith('jpg')]) == 20


def test_transfer_workflow(client, mock_dbus, tmpdir):
    wfid = create_workflow(client, 10)
    client.post('/workflow/{0}/transfer'.format(wfid))
    assert len([x for x in tmpdir.visit('stick/*/raw/*.jpg')]) == 20


def test_submit_workflow(app, tmpdir):
    app.config['postproc_server'] = 'http://127.0.0.1:5000'
    app.config['mode'] = 'scanner'
    client = app.test_client()
    wfid = create_workflow(client)
    with mock.patch('spreadsplug.web.web.requests.post') as post:
        post.return_value.json = {'id': 1}
        client.post('/workflow/{0}/submit'.format(wfid))
    wfname = json.loads(client.get('/workflow/{0}'.format(wfid)).data)['name']
    for img in tmpdir.join(wfname, 'raw').listdir():
        post.assert_any_call('http://127.0.0.1:5000/workflow/{0}/image'
                             .format(wfid),
                             files={'file': {
                                 img.basename: img.open('rb').read()}})
    post.assert_any_call('http://127.0.0.1:5000/queue',
                         data=json.dumps({'id': wfid}))


def test_add_to_queue(client, tmpdir, worker):
    wfid = create_workflow(client)
    rv = client.post('/queue', data=json.dumps({'id': wfid}))
    assert json.loads(rv.data)['queue_position'] == 1
    wfname = json.loads(client.get('/workflow/{0}'.format(wfid)).data)['name']
    time.sleep(5)
    assert tmpdir.join(wfname, 'processed_a.txt').exists()
    assert tmpdir.join(wfname, 'processed_b.txt').exists()
    assert tmpdir.join(wfname, 'output.txt').exists()
    assert len(json.loads(client.get('/queue').data)) == 0


def test_list_jobs(client, worker):
    wfids = [create_workflow(client) for x in xrange(3)]
    for wfid in wfids:
        client.post('/queue', data=json.dumps({'id': wfid}))
    jobs = json.loads(client.get('/queue').data)
    assert len(jobs) == 3


def test_remove_from_queue(client):
    wfids = [create_workflow(client) for x in xrange(3)]
    jobids = [json.loads(client.post('/queue', data=json.dumps({'id': wfid}))
                         .data)['queue_position']
              for wfid in wfids]
    client.delete('/queue/{0}'.format(jobids[0]))
    jobs = json.loads(client.get('/queue').data)
    assert len(jobs) == 2


def test_upload_workflow_image(client, tmpdir):
    wfid = create_workflow(client, num_captures=None)
    client.post('/workflow/{0}/image'.format(wfid),
                data={'file': ('./tests/data/even.jpg', '000.jpg')})
    wfdata = json.loads(client.get('/workflow/{0}'.format(wfid)).data)
    assert len(wfdata['images']) == 1
    assert tmpdir.join(wfdata['name'], 'raw', '000.jpg').exists()
    resp = client.post('/workflow/{0}/image'.format(wfid),
                       data={'file': ('./tests/data/even.jpg', '000.png')})
    assert resp.status_code == 500


def test_get_workflow_image(client):
    wfid = create_workflow(client)
    with open(os.path.abspath('./tests/data/even.jpg'), 'rb') as fp:
        orig = fp.read()
    fromapi = client.get('/workflow/{0}/image/0'.format(wfid)).data
    assert orig == fromapi


def test_get_workflow_image_scaled(client):
    wfid = create_workflow(client)
    img = jpegtran.JPEGImage(blob=client.get(
        '/workflow/{0}/image/0?width=300'.format(wfid)).data)
    assert img.width == 300


def test_get_workflow_image_thumb(client):
    # TODO: Use test images that actually have an EXIF thumbnail...
    wfid = create_workflow(client)
    rv = client.get('/workflow/{0}/image/1/thumb'.format(wfid))
    assert rv.status_code == 200
    assert jpegtran.JPEGImage(blob=rv.data).width


def test_prepare_capture(client):
    wfid = create_workflow(client, num_captures=None)
    rv = client.post('/workflow/{0}/prepare_capture'.format(wfid))
    assert rv.status_code == 200
    # TODO: Verify workflow was prepared, verify right data
    #       was returned


def test_prepare_capture_when_other_active(client):
    wfid = create_workflow(client, num_captures=None)
    client.post('/workflow/{0}/prepare_capture'.format(wfid))
    client.post('/workflow/{0}/capture'.format(wfid))
    wfid = create_workflow(client, num_captures=None)
    assert (client.post('/workflow/{0}/prepare_capture'.format(wfid))
            .status_code) == 200


def test_capture(client):
    wfid = create_workflow(client, num_captures=None)
    assert (client.post('/workflow/{0}/prepare_capture'.format(wfid))
            .status_code) == 200
    assert (client.post('/workflow/{0}/capture'.format(wfid))
            .status_code) == 200
    # TODO: Verify it was triggered on the workflow, verify
    #       the right data was returned


def test_finish_capture(client):
    wfid = create_workflow(client, num_captures=None)
    assert (client.post('/workflow/{0}/prepare_capture'.format(wfid))
            .status_code) == 200
    assert (client.post('/workflow/{0}/capture'.format(wfid))
            .status_code) == 200
    assert (client.post('/workflow/{0}/finish_capture'.format(wfid))
            .status_code) == 200


def test_shutdown(client):
    with mock.patch('spreadsplug.web.web.subprocess.call') as sp:
        client.post('/system/shutdown')
    sp.assert_called_once_with(['/usr/bin/sudo',
                                '/sbin/shutdown', '-h', 'now'])
