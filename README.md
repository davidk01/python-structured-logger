# Introduction

Basic context manager for logging/tracing. Out of the box there is one tracer to serve as an example but
I might add a few more to show how to initialize multiple tracers that write/send the data to some place
other than the standard output stream. The context is nestable and each nesting pushes a new data dictionary
onto the internal stack to be populated by the context block. The data is then given to the backends in
reverse order when the nested contexts exit.

The idea is that within the context block callers can incrementally
populate "trace" data and when the context block exits the populated dictionary is passed on to the
logging/tracing backends to do with as they wish. The example tracer just logs to the standard output
stream but one can imagine sending the populated dictionary to something like NATS, Kafka, StackDriver, etc.

# Usage

```python
import structuredlogger.tracer as tracer

t = tracer.TracerContextManager()
def test():
    with t:
        t.current_data.update({'a': 'a', 'b': 'b'})
        t.current_data.update({'c': 'c', 'd': 'd'})
        print 'Doing some stuff'
        with t:
            t.current_data.update({'e': 'e', 'f': 'f'})
            print 'Doing some more stuff'

test()
```

Running the above will output the following

```
Doing some stuff
Doing some more stuff
{"thread": "MainThread", "start_time": "2018-02-24T06:22:19.329125+00:00",
"process_name": "python example.py", "pid": 30754, "file": "example.py", "duration": 0.006336,
"line": 12, "data": {"e": "e", "f": "f"}, "function_name": "test"}
{"thread": "MainThread", "start_time": "2018-02-24T06:22:19.329042+00:00",
"process_name": "python example.py", "pid": 30754, "file": "example.py", "duration": 0.00692,
"line": 12, "data": {"a": "a", "c": "c", "b": "b", "d": "d"}, "function_name": "test"}
```
