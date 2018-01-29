# --
# Copyright (c) 2008-2018 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

from __future__ import absolute_import

import logging
import logging.config

import configobj

from nagare import log
from nagare.services import plugin

# -----------------------------------------------------------------------------

logging._srcfile = __file__[:-1] if __file__.endswith(('.pyc', '.pyo')) else __file__
logging.addLevelName(10000, 'NONE')

# -----------------------------------------------------------------------------


class Logger(plugin.Plugin):
    CONFIG_SPEC = configobj.ConfigObj({
        'logger': {
            'level': 'string(default="INFO")',
            'propagate': 'boolean(default=True)'
        },
        'handler': {
            'class': 'string(default=None)',
        },
        'formatter': {
            'format': 'string(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")'
        }
    }, interpolation=False)

    def __init__(self, name, dist, **config):
        super(Logger, self).__init__(name, dist, **config)
        self.config = config

    @staticmethod
    def configure(app_logger, logger, handler, formatter, **sections):
        logger_name = 'nagare.application.' + app_logger
        log.set_logger(logger_name)

        if not handler['class']:
            handler['class'] = 'logging.StreamHandler'
            handler.setdefault('stream', 'ext://sys.stderr')

        loggers = {logger_name: dict(logger, handlers=[logger_name])}
        handlers = {logger_name: dict(handler, formatter=logger_name)}
        formatters = {logger_name: formatter}

        for name, config in sections.items():
            if name.startswith('logger_'):
                name = config.pop('qualname')
                if name.startswith('.'):
                    name = logger_name + name

                config['propagate'] = config.get('propagate', '1') == '1'

                handler = config.get('handlers')
                if handler:
                    config['handlers'] = handler.split(',')

                loggers[name] = config

            if name.startswith('handler_'):
                handlers[name[8:]] = config

            if name.startswith('formatter_'):
                formatters[name[10:]] = config

        logging_config = {
            'version': 1,

            'loggers': loggers,
            'handlers': handlers,
            'formatters': formatters
        }

        logging.config.dictConfig(logging_config)

    def handle_start(self, app):
        self.configure(app.name, **self.config)
