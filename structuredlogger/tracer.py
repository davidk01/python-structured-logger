from __future__ import print_function
import datetime
import pytz
import inspect
import sys
import threading
import json
import logging
import os
import subprocess


class TracerInterface(object):
    def trace(self, payload=None):
        raise NotImplementedError('Implement in subclass')


class Utils(object):
    """
    Some static helper methods
    """
    @staticmethod
    def init_logger(cls, lock=None):
        if lock is None:
            raise Exception('Provide a lock for initializing the class level logger')
        with lock:
            if cls._logger is None:
		logger = logging.getLogger('{}.{}'.format(__file__, cls.__name__))
                logger.propagate = False
                logger.setLevel(logging.ERROR)
                ch = logging.StreamHandler(stream=sys.stdout)
                ch.setLevel(logging.ERROR)
                formatter = logging.Formatter('%(message)s')
                ch.setFormatter(formatter)
                logger.addHandler(ch)
                cls._logger = logger

    @staticmethod
    def now():
        return pytz.utc.localize(datetime.datetime.utcnow())


class ConsoleTracer(TracerInterface):
    """
    Just print everything to STDOUT
    """
    _logger = None
    _logger_lock = threading.Lock()

    @classmethod
    def get_logger(cls):
        Utils.init_logger(cls, cls._logger_lock)

    def __init__(self, logger=None):
        if logger is None:
            self.get_logger()
        else:
            self._logger = logger

    def trace(self, payload=None):
        """
        Dump the payload as JSON to STDOUT
        """
        if payload is not None:
            try:
                print(json.dumps(payload))
                # Have to flush otherwise the output is delayed. Not an issue if
                # the incoming rate is high enough but still a good idea to flush
                # nonetheless
                sys.stdout.flush()
            except Exception as e:
                self._logger.error(e)


class TracerContextManager(object):
    """
    Context manager for shipping tracing information to various backends, e.g.
    OpenTracing, Kafka, StackDriver, Structlog, etc.
    """
    # The tracing context is a dictionary that context callers get to write whatever they want
    # to. These are some of the reserved keys we use to track default bits of information
    _data_key = 'data'
    _start_time_key = 'start_time'
    _duration_key = 'duration'
    _file_key = 'file'
    _line_key = 'line'
    _function_key = 'function_name'
    _thread_key = 'thread'
    _pid_key = 'pid'
    _process_name_key = 'process_name'

    _logger = None
    _logger_lock = threading.Lock()

    @classmethod
    def get_logger(cls):
        Utils.init_logger(cls, cls._logger_lock)

    def __init__(self, tracer_shippers=None, logger=None):
        if tracer_shippers is None:
            tracer_shippers = [ConsoleTracer()]
        self._tracer_shippers = tracer_shippers
        if logger is None:
            self.get_logger()
        else:
            self._logger = logger
        # Every time we enter we push a new dictionary onto the context stack and
        # every time we exit we pop the dictionary and send it to the tracers. Lists
        # are good enough stacks in a pinch
        self._context_stack = []
        # PID and process name are stable so we just get them once and re-use them
        self.__pid = os.getpid()
        def __process_name(pid):
            process_name = ''
            try:
                command = ["cat", "/proc/{}/cmdline".format(pid)]
                output = subprocess.check_output(command)
                delimiter = '\x00'
                # The output is a string with null separators so we have to parse those out
                process_name = ' '.join(output.split(delimiter)[:-1])
            except Exception as e:
                self._logger.error(e)
            return process_name
        self.__process_name = __process_name(self.__pid)

    @property
    def current_data(self):
        """
        For wholesale mutation of the context context callers can just get everything and
        populate it all in one go if they want, e.g. Tracer.context.update(dict)
        """
        return self._context_stack[-1][self._data_key]

    def _trace(self, payload=None):
        """
        Just iterate and call each tracer. We don't worry about exceptions other
        than logging them
        """
        if payload is None:
            payload = self._context_stack[-1]

        for trace_shipper in self._tracer_shippers:
            try:
                trace_shipper.trace(payload=payload)
            except Exception as e:
                self._logger.error(e)

    def _enrich(self, payload=None):
        """
        Before we send the payload to be traced we "enrich" it with some information to help us
        better pinpoint the source of the event
        """
        if payload is None:
            return
        frame = inspect.currentframe()
        outer_frames = inspect.getouterframes(frame)
        _, filename, line, name, _, _ = outer_frames[2]
        thread_name = threading.current_thread().name
        pid = self.__pid
        process_name = self.__process_name
        duration = Utils.now() - payload[self._start_time_key]
        payload.update({
            self._file_key: filename,
            self._line_key: line,
            self._function_key: name,
            self._thread_key: thread_name,
            self._pid_key: pid,
            self._process_name_key: process_name,
            self._duration_key: duration,
        })

    def _convert(self, payload=None):
        """
        After enrichment we also perform some conversions of some keys to serialized forms because we don't
        expect to perform any more calculations and can format them as we want the downstream tracers to see them
        """
        if payload is None:
            return
        payload[self._start_time_key] = payload[self._start_time_key].isoformat()
        payload[self._duration_key] = payload[self._duration_key].total_seconds()

    def __enter__(self):
        """
        Create an empty dictionary so that it can be populated as tracing
        is happening. By default we populate the start time and potentially a few
        more things we know we definitely want to trace. The rest of the keys
        will be populated in the data dictionary so that they don't trample
        our default keys
        """
        context = {
            self._start_time_key: Utils.now(),
            self._data_key: { }
        }
        self._context_stack.append(context)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """
        Grab the current context, enrich it, perform any necessary serialization conversions, and
        finally ship to the tracers
        """
        # Pop the current context and ship it to the tracers
        payload = self._context_stack.pop()
        self._enrich(payload=payload)
        self._convert(payload=payload)
        self._trace(payload=payload)
        return False
