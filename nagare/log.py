# --
# Copyright (c) 2008-2018 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

import logging

logger_name = None


def set_logger(name):
    global logger_name

    logger_name = name


def get_logger(name=None):
    global logger_name

    if name is None:
        name = '.'

    if name.startswith('.'):
        name = (logger_name + name) if logger_name else 'nagare.application'

    return logging.getLogger(name.rstrip('.'))


def debug(msg, *args, **kw):
    get_logger().debug(msg, *args, **kw)


def info(msg, *args, **kw):
    get_logger().info(msg, *args, **kw)


def warning(msg, *args, **kw):
    get_logger().warning(msg, *args, **kw)


def error(msg, *args, **kw):
    get_logger().error(msg, *args, **kw)


def critical(msg, *args, **kw):
    get_logger().critical(msg, *args, **kw)


def exception(msg, *args):
    get_logger().exception(msg, *args)


def log(level, msg, *args, **kw):
    get_logger().log(level, msg, *args, **kw)
