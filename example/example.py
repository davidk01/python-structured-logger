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
