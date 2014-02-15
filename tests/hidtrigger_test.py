import time
from itertools import chain, repeat

import mock
import pytest

import spreadsplug.hidtrigger as hidtrigger


@pytest.fixture
def plugin():
    return hidtrigger.HidTrigger(config=None)


@mock.patch('spreadsplug.hidtrigger.hid.enumerate')
@mock.patch('spreadsplug.hidtrigger.hid.device')
def test_trigger_loop(devicecls, hid_enumerate, plugin):
    mock_dev = mock.Mock()
    mock_dev.read.side_effect = chain(
        list(chain(repeat(None, 10), ('foo',), repeat(None, 10), ('bar',)))*6,
        repeat(None))
    hid_enumerate.return_value = [{'vendor_id': 'foo', 'product_id': 'bar'}]
    devicecls.return_value = mock_dev
    mock_cb = mock.Mock()
    plugin.start_trigger_loop(mock_cb)
    time.sleep(1.3)
    plugin.stop_trigger_loop()
    assert not plugin._loop_thread.is_alive()
    assert mock_cb.call_count == 6
