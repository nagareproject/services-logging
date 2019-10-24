# --
# Copyright (c) 2008-2019 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

from __future__ import absolute_import

import logging
import logging.config
import traceback
from os import path

import colorama
import configobj
import backtrace

from nagare import log
from nagare.services import plugin

COLORS = {'': ''}
COLORS.update(colorama.Fore.__dict__)
COLORS.update(colorama.Style.__dict__)

STYLES = {
    'nocolors': {
        'backtrace': '',
        'error': '',
        'line': '',
        'module': '',
        'context': '',
        'call': ''
    },
    'light': {
        'backtrace': 'YELLOW',
        'error': 'RED',
        'line': 'RED',
        'module': '',
        'context': 'GREEN',
        'call': 'BLUE'
    },
    'dark': {
        'backtrace': 'YELLOW',
        'error': 'RED',
        'line': 'RED',
        'module': '',
        'context': 'BRIGHT GREEN',
        'call': 'YELLOW'
    }
}

CATEGORIES = [
    {
        'call': '%s-> ' + COLORS['BRIGHT']
    },
    {
        'line': 'at line %s',
        'module': 'File %s',
        'context': 'in %s',
        'call': '%s-> ' + COLORS['BRIGHT']
    }
]

# -----------------------------------------------------------------------------


logging._srcfile = __file__[:-1] if __file__.endswith(('.pyc', '.pyo')) else __file__
logging.addLevelName(10000, 'NONE')

# -----------------------------------------------------------------------------


class ColorizingStreamHandler(logging.StreamHandler):
    def __init__(self, style='nocolors', simplified=True, conservative=True, reverse=False, align=True, keep_path=2):
        super(ColorizingStreamHandler, self).__init__()

        self.style = style
        self.simplified = simplified
        self.conservative = conservative
        self.reverse = reverse
        self.align = align
        self.keep_path = keep_path

    def emit(self, record):
        isatty = getattr(self.stream, 'isatty', lambda: False)()
        if not (isatty and record.exc_info and self.style):
            super(ColorizingStreamHandler, self).emit(record)
        else:
            exc_type, exc_value, exc_tb = record.exc_info

            record.exc_info = None
            super(ColorizingStreamHandler, self).emit(record)

            tb = last_chain_seen = exc_tb
            while self.simplified and tb:
                func_name = tb.tb_frame.f_code.co_name
                tb = tb.tb_next
                if (tb is not None) and (func_name == 'handle_request'):
                    last_chain_seen = tb

            if not last_chain_seen:
                last_chain_seen = exc_tb

            tb = []
            for entry in traceback.extract_tb(last_chain_seen):
                filename = entry[0].split(path.sep)
                filename = path.sep.join(filename[-self.keep_path or None:])
                tb.append((filename,) + entry[1:])

            parser = backtrace._Hook(
                reversed(tb) if self.reverse else tb,
                self.align,
                conservative=self.conservative
            )

            trace = parser.generate_backtrace(self.style)
            type_ = exc_type if isinstance(exc_type, str) else exc_type.__name__
            tb_message = self.style['backtrace'].format('Traceback ({}):'.format(
                'Most recent call ' + ('first' if self.reverse else 'last')
            ))
            err_message = self.style['error'].format(type_ + ': ' + repr(exc_value) + COLORS['RESET_ALL'])

            self.stream.write(tb_message + '\n')
            if self.reverse:
                self.stream.write(err_message + '\n')

            self.stream.write('\n'.join(line.rstrip() for line in trace) + '\n')

            if not self.reverse:
                self.stream.write(err_message + '\n')

            self.flush()


class Logger(plugin.Plugin):
    LOAD_PRIORITY = 0
    CONFIG_SPEC = configobj.ConfigObj({
        '_app_name': 'string(default=$app_name)',

        'logger': {
            'level': 'string(default="INFO")',
            'propagate': 'boolean(default=False)'
        },
        'handler': {
            'class': 'string(default=None)',
        },
        'formatter': {
            'format': 'string(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")'
        },

        'logger_exceptions': {
            'qualname': 'string(default="nagare.services.exceptions")',
            'level': 'string(default="DEBUG")',
            'propagate': 'boolean(default=False)'
        },

        'exceptions': {
            'style': 'string(default=nocolors)',
            'simplified': 'boolean(default=True)',
            'conservative': 'boolean(default=True)',
            'reverse': 'boolean(default=False)',
            'align': 'boolean(default=True)',
            'keep_path': 'integer(default=2)',
            '__many__': {
                'backtrace': 'string(default="")',
                'error': 'string(default="")',
                'line': 'string(default="")',
                'module': 'string(default="")',
                'context': 'string(default="")',
                'call': 'string(default="")'
            }
        }
    }, interpolation=False)

    def __init__(self, name, dist, _app_name, exceptions, logger, handler, formatter, **sections):
        super(Logger, self).__init__(name, dist)

        # Application logger
        # ------------------

        logger_name = 'nagare.application.' + _app_name
        log.set_logger(logger_name)

        logger['level'] = logger['level'] or 'ERROR'

        if not handler['class']:
            handler['class'] = 'logging.StreamHandler'
            handler.setdefault('stream', 'ext://sys.stderr')

        loggers = {logger_name: dict(logger, handlers=[logger_name])}
        handlers = {logger_name: dict(handler, formatter=logger_name)}
        formatters = {logger_name: formatter}

        # Other loggers
        # -------------

        for name, config in sections.items():
            if name.startswith('logger_'):
                name = config.pop('qualname')
                if name.startswith('.'):
                    name = logger_name + name

                if name == 'root':
                    name = ''

                config['propagate'] = config.get('propagate', '1') == '1'

                handler = config.get('handlers')
                if handler:
                    config['handlers'] = handler.split(',')

                loggers[name] = config

            if name.startswith('handler_'):
                handlers[name[8:]] = config

            if name.startswith('formatter_'):
                formatters[name[10:]] = config

        # Root logger
        # -----------

        root = loggers.get('', {})
        root.setdefault('level', 'INFO')

        if 'handlers' not in root:
            root['handlers'] = ['_root_handler']

            handlers['_root_handler'] = {
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stderr'
            }

        loggers[''] = root

        logging_config = {
            'version': 1,

            'loggers': loggers,
            'handlers': handlers,
            'formatters': formatters
        }

        logging.config.dictConfig(logging_config)

        # Colorized exceptions
        # --------------------

        handler = self.create_exception_handler(**exceptions)
        if handler is not None:
            logging.getLogger('nagare.services.exceptions').addHandler(handler)

    @staticmethod
    def create_exception_handler(style, simplified, conservative, reverse, align, keep_path, **styles):
        style = (styles.get(style) or STYLES.get(style, {})).copy()

        if not style:
            handler = None
        else:
            colorama.init(autoreset=True)

            for category, colors in style.items():
                color = ''.join(COLORS.get(color.upper(), '') for color in colors.split())
                style[category] = (CATEGORIES[conservative].get(category, '%s') % color) + '{}'

            handler = ColorizingStreamHandler(style, simplified, conservative, reverse, align, keep_path)

        return handler
