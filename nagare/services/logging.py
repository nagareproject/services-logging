# --
# Copyright (c) 2008-2021 Net-ng.
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
from collections import OrderedDict

import colorama
import configobj
from chromalog import ColorizingStreamHandler, colorizer

from nagare import log
from nagare.services import plugin, backtrace

COLORS = {'': ''}
COLORS.update(colorama.Fore.__dict__)
COLORS.update(colorama.Style.__dict__)
COLORS.update({'BACK_' + color_name: color for color_name, color in colorama.Back.__dict__.items()})

STYLES = {
    'nocolors': {
        'debug': [],
        'info': [],
        'warning': [],
        'error': [],
        'critical': [],

        'backtrace': [],
        'line': [],
        'module': [],
        'context': [],
        'call': []
    },
    'light': {
        'debug': ['CYAN'],
        'info': [],
        'warning': ['YELLOW'],
        'error': ['RED'],
        'critical': ['BACK_RED'],

        'backtrace': ['YELLOW'],
        'line': ['RED'],
        'module': [],
        'context': ['GREEN'],
        'call': ['BLUE'],

    },
    'dark': {
        'debug': ['CYAN'],
        'info': [],
        'warning': ['YELLOW'],
        'error': ['RED'],
        'critical': ['BACK_RED'],

        'backtrace': ['YELLOW'],
        'line': ['RED'],
        'module': [],
        'context': ['BRIGHT', 'GREEN'],
        'call': ['YELLOW']
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


class ColorizingExceptionHandler(logging.StreamHandler):
    def __init__(self, style='nocolors', simplified=True, conservative=True, reverse=False, align=True, keep_path=2):
        super(ColorizingExceptionHandler, self).__init__()

        self.style = style
        self.simplified = simplified
        self.conservative = conservative
        self.reverse = reverse
        self.align = align
        self.keep_path = keep_path

    def emit(self, record):
        isatty = getattr(self.stream, 'isatty', lambda: False)()
        if not (isatty and record.exc_info and self.style):
            super(ColorizingExceptionHandler, self).emit(record)
        else:
            exc_type, exc_value, exc_tb = record.exc_info

            record.exc_info = None
            super(ColorizingExceptionHandler, self).emit(record)

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


class DictConfigurator(logging.config.dictConfigClass):
    def __init__(self):
        pass

    def create_handler(self, args='()', **kw):
        cls = self.resolve(kw.pop('class'))

        # Special case for handler which refers to another handler
        # (see `logging.config.DictConfigurator.configure_handler`)
        if issubclass(cls, logging.handlers.SMTPHandler) and ('mailhost' in kw):
            mailhost = kw['mailhost']
            if isinstance(mailhost, (list, tuple)):
                kw['mailhost'] = (mailhost[0], int(mailhost[1]))
        elif issubclass(cls, logging.handlers.SysLogHandler) and ('address' in kw):
            address = kw['address']
            if isinstance(address, (list, tuple)):
                kw['address'] = (address[0], int(address[1]))

        return cls(**kw) if kw else cls(*eval(args))

    def configure(self, config):
        super(DictConfigurator, self).__init__(config)
        super(DictConfigurator, self).configure()


class Logger(plugin.Plugin):
    LOAD_PRIORITY = 0
    CONFIG_SPEC = configobj.ConfigObj(dict(
        plugin.Plugin.CONFIG_SPEC,
        _app_name='string(default=$app_name)',

        style='string(default=nocolors)',
        styles={
            '__many__': {
                'debug': 'list(default=list)',
                'info': 'list(default=list)',
                'warning': 'list(default=list)',
                'error': 'list(default=list)',
                'critical': 'list(default=list)',

                'backtrace': 'list(default=list)',
                'line': 'list(default=list)',
                'module': 'list(default=list)',
                'context': 'list(default=list)',
                'call': 'list(default=list)'
            }
        },

        logger={
            'level': 'string(default="INFO")',
            'propagate': 'boolean(default=False)'
        },
        handler={
            'class': 'string(default=None)',
        },
        formatter={
            'format': 'string(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")'
        },

        logger_exceptions={
            'qualname': 'string(default="nagare.services.exceptions")',
            'level': 'string(default="DEBUG")',
            'propagate': 'boolean(default=False)'
        },

        exceptions={
            'simplified': 'boolean(default=True)',
            'conservative': 'boolean(default=True)',
            'reverse': 'boolean(default=False)',
            'align': 'boolean(default=True)',
            'keep_path': 'integer(default=2)'
        }
    ), interpolation=False)

    @classmethod
    def get_plugin_spec(cls):
        return OrderedDict(sorted(cls.CONFIG_SPEC.dict().items()))

    def __init__(
            self,
            name, dist,
            _app_name,
            style, styles,
            logger, handler, formatter,
            exceptions,
            **sections
    ):
        super(Logger, self).__init__(
            name, dist,
            style=style, styles=styles,
            logger=logger, handler=handler, formatter=formatter,
            exceptions=exceptions,
            **sections
        )
        colorama.init(autoreset=True)

        colors = (styles.get(style) or STYLES.get(style) or STYLES['nocolors']).copy()
        colors = {name: ''.join(COLORS.get(c.upper(), '') for c in color) for name, color in colors.items()}

        configurator = DictConfigurator()

        # Application logger
        # ------------------

        logger_name = 'nagare.application.' + _app_name
        log.set_logger(logger_name)

        logger['level'] = logger['level'] or 'ERROR'

        if not handler['class']:
            handler['class'] = 'logging.StreamHandler'
            handler.setdefault('stream', 'ext://sys.stderr')

        handler['()'] = configurator.create_handler

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
                handlers[name[8:]]['()'] = configurator.create_handler

            if name.startswith('formatter_'):
                formatters[name[10:]] = config

        # Root logger
        # -----------

        root = loggers.get('', {})
        root.setdefault('level', 'INFO')

        if 'handlers' not in root:
            root['handlers'] = ['_root_handler']

            handlers['_root_handler'] = {
                'stream': 'ext://sys.stderr',
                'formatter': '_root_formatter',
                '()': lambda stream: ColorizingStreamHandler(
                    stream,
                    colorizer.GenericColorizer(
                        {name: (color, COLORS['RESET_ALL']) for name, color in colors.items()}
                    )
                )
            }

            formatters['_root_formatter'] = {
                'class': 'chromalog.ColorizingFormatter',
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            }

        loggers[''] = root

        logging_config = {
            'version': 1,

            'loggers': loggers,
            'handlers': handlers,
            'formatters': formatters
        }

        configurator.configure(logging_config)

        # Colorized exceptions
        # --------------------

        exception_logger = logging.getLogger('nagare.services.exceptions')
        if style and not exception_logger.handlers:
            handler = self.create_exception_handler(colors, **exceptions)
            exception_logger.addHandler(handler)

    @staticmethod
    def create_exception_handler(colors, simplified, conservative, reverse, align, keep_path, **styles):
        colors = {
            category: (CATEGORIES[conservative].get(category, '%s') % color) + '{}'
            for category, color
            in colors.items()
        }

        return ColorizingExceptionHandler(colors, simplified, conservative, reverse, align, keep_path)
