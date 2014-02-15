# -*- coding: utf-8 -*-

import logging
import subprocess

from concurrent import futures
from jpegtran import JPEGImage

from spreads.plugin import HookPlugin

logger = logging.getLogger('spreadsplug.autorotate')


def autorotate_image(path):
    print "Rotating " + path
    img = JPEGImage(path)
    if img.exif_orientation is None:
        logger.warn("Image {0} did not have any EXIF rotation, did not rotate."
                    .format(path))
        return
    elif img.exif_orientation == 1:
        logger.info("Image {0} is already rotated.".format(path))
        return
    rotated = img.exif_autotransform()
    rotated.save(path)


class AutoRotatePlugin(HookPlugin):
    __name__ = 'autorotate'

    def process(self, path):
        img_dir = path / 'raw'
        logger.info("Rotating images in {0}".format(img_dir))
        with futures.ProcessPoolExecutor() as executor:
            for imgpath in sorted(img_dir.iterdir()):
                if imgpath.lower()[-4:] not in ('.jpg', 'jpeg'):
                    continue
                executor.submit(autorotate_image, unicode(imgpath))
