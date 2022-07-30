# --
# Copyright (c) 2008-2022 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

from __future__ import absolute_import

import sys
import logging
import logging.config
import traceback
from os import path

import colorama
import chromalog
from chromalog import ColorizingFormatter  # noqa: F401

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
        'debug': ['GREEN'],
        'info': [],
        'warning': ['YELLOW'],
        'error': ['BRIGHT', 'RED'],
        'critical': ['BACK_RED', 'BRIGHT', 'WHITE'],

        'backtrace': ['YELLOW'],
        'line': ['YELLOW'],
        'module': [],
        'context': ['GREEN'],
        'call': [],

    },
    'dark': {
        'debug': ['DIM', 'GREEN'],
        'info': [],
        'warning': ['DIM', 'YELLOW'],
        'error': ['RED'],
        'critical': ['BACK_RED', 'WHITE'],

        'backtrace': ['YELLOW'],
        'line': ['YELLOW'],
        'module': [],
        'context': ['GREEN'],
        'call': []
    }
}

CATEGORIES = [
    {
        'call': '%s-> ' + COLORS['BRIGHT']
    },
    {
        'backtrace': '%s',
        'error': '%s',
        'line': 'at line %s',
        'module': 'File %s',
        'context': 'in %s',
        'call': '%s-> ' + COLORS['BRIGHT']
    }
]

DEFAULT_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# -----------------------------------------------------------------------------


logging._srcfile = __file__[:-1] if __file__.endswith(('.pyc', '.pyo')) else __file__
logging.addLevelName(10000, 'NONE')

DefaultColorizingStreamHandler = None

# -----------------------------------------------------------------------------


class ColorizingStreamHandler(chromalog.ColorizingStreamHandler):

    def __init__(
        self,
        stream=sys.stderr,
        colors=None,
        simplified=True, conservative=True, reverse=False, align=True, keep_path=2
    ):
        colors = colors or {}

        super(ColorizingStreamHandler, self).__init__(
            stream,
            chromalog.colorizer.MonochromaticColorizer({
                name: (color, COLORS['RESET_ALL'])
                for name, color
                in colors.items()
            })
        )

        self.simplified = simplified
        self.conservative = conservative
        self.reverse = reverse
        self.align = align
        self.keep_path = keep_path

        self.style = {
            category: (CATEGORIES[conservative].get(category, '%s') % color) + '{}'
            for category, color
            in colors.items()
            if category in CATEGORIES[1]
        }

    def emit(self, record):
        isatty = getattr(self.stream, 'isatty', lambda: False)()
        if not (isatty and record.exc_info and self.style):
            super(ColorizingStreamHandler, self).emit(record)
        else:
            exc_type, exc_value, exc_tb = record.exc_info

            if exc_type is SyntaxError:
                super(ColorizingStreamHandler, self).emit(record)
            else:
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


class DefaultColorizingStreamHandler:
    CONFIG = {}

    def __new__(cls, *args, **kw):
        config = cls.CONFIG.copy()
        config.update(kw)

        return ColorizingStreamHandler(*args, **config)


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
    CONFIG_SPEC = dict(
        plugin.Plugin.CONFIG_SPEC,
        _app_name='string(default="$app_name")',

        style='string(default=nocolors, help="color theme")',
        styles={
            '__many__': {
                'debug': 'string_list(default=list(), help="color for the ``debug`` level log messages")',
                'info': 'string_list(default=list(), help="color for the ``info`` level log messages")',
                'warning': 'string_list(default=list(), help="color for the ``warning`` level log messages")',
                'error': 'string_list(default=list(), help="color for the ``error`` level log messages")',
                'critical': 'string_list(default=list(), help="color for the ``critical`` level log messages")',

                'backtrace': 'string_list(default=list())',
                'line': 'string_list(default=list())',
                'module': 'string_list(default=list())',
                'context': 'string_list(default=list())',
                'call': 'string_list(default=list())'
            }
        },

        exceptions={
            'simplified': 'boolean(default=True, help="Don\'t display the first Nagare internal call frames")',
            'conservative': 'boolean(default=True, help="")',
            'reverse': 'boolean(default=False, help="Display the call frames in reverse order (last called frame fist)")',
            'align': 'boolean(default=True, help="align the fields of the call frames")',
            'keep_path': 'integer(default=2, help="number of last filename parts to display. ``0`` to display the whole filename")'
        },

        logger={
            'propagate': 'boolean(default=True, help="propagate log messages to the parent logger")',
            'handlers': 'string_list(default=list(), help="list of handlers to use")',
            '___many___': 'string'
        },
        handler={},
        formatter={},

        __many__={
            'level': 'string(default="INFO")',
            'propagate': 'boolean(default=True, help="propagate log messages to the parent logger")',
            'handlers': 'string_list(default=list(), help="list of handlers to use")'
        },

        loggers={
            'root': {
                'qualname': 'string(default="root")',
                'level': 'string(default="INFO")',
                'handlers': 'string_list(default=list(root), help="list of handlers to use")'
            },
            '__many__': {
                'qualname': 'string',
                'propagate': 'boolean(default=True, help="propagate log messages to the parent logger")',
                'handlers': 'string_list(default=list(), help="list of handlers to use")'
            }
        },
        handlers={
            'root': {
                'class': 'string(default="nagare.services.logging.DefaultColorizingStreamHandler")',
                'formatter': 'string(default="root")'
            },
            '__many__': {}
        },
        formatters={
            'root': {
                'class': 'string(default="nagare.services.logging.ColorizingFormatter")',
                'format': 'string(default="{}")'.format(DEFAULT_FORMAT)
            },
            '__many__': {}
        }
    )

    def __init__(
            self,
            name, dist,
            _app_name,
            style, styles,
            exceptions,
            logger, handler, formatter,
            loggers, handlers, formatters,
            **sections
    ):
        colorama.init(autoreset=True)

        DefaultColorizingStreamHandler.CONFIG = {k: v for k, v in exceptions.items() if not isinstance(v, dict)}

        colors = (styles.get(style) or STYLES.get(style) or STYLES['nocolors']).copy()
        colors = {name: ''.join(COLORS.get(c.upper(), '') for c in color) for name, color in colors.items()}
        DefaultColorizingStreamHandler.CONFIG['colors'] = colors

        configurator = DictConfigurator()

        logger_name = 'nagare.application.' + _app_name
        log.set_logger(logger_name)

        # Other loggers
        # -------------

        for name, config in sections.items():
            if '_' in name:
                category, name = name.split('_', 1)
                if category == 'logger':
                    loggers[name] = config

                elif category == 'handler':
                    handlers[name] = {k: v for k, v in config.items() if k not in {'level', 'propagate', 'handlers'}}

                elif category == 'formatter':
                    formatters[name] = {k: v for k, v in config.items() if k not in {'level', 'propagate', 'handlers'}}

        loggers = {self.absolute_qualname(logger_name, logger['qualname']): logger for logger in loggers.values()}
        for handler_config in handlers.values():
            handler_config['()'] = configurator.create_handler

        # Application logger
        # ------------------

        if logger_name not in loggers:
            logger['qualname'] = logger_name
            formatters[logger_name] = formatter

            if handler:
                handler.setdefault('()', configurator.create_handler)
                if formatter:
                    handler['formatter'] = logger_name

                handlers[logger_name] = handler
                logger['handlers'] = [logger_name]

            loggers[logger_name] = logger

        logging_config = {
            'version': 1,

            'loggers': loggers,
            'handlers': handlers,
            'formatters': formatters
        }

        configurator.configure(logging_config)

        for handler in handlers.values():
            del handler['()']
        loggers['root'] = loggers.pop('')

        super(Logger, self).__init__(
            name, dist,
            style=style, styles=styles,
            exceptions=exceptions,
            loggers=loggers, handlers=handlers, formatters=formatters
        )

    @staticmethod
    def absolute_qualname(app_logger_name, qualname):
        if qualname.startswith('.'):
            qualname = app_logger_name + ('' if qualname == '.' else qualname)

        if qualname == 'root':
            qualname = ''

        return qualname
