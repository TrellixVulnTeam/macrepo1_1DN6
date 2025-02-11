# Testing the line trace facility.

from test import support
import unittest
import sys
import difflib
import gc
from functools import wraps

class tracecontext:
    """Contex manager that traces its enter and exit."""
    def __init__(self, output, value):
        self.output = output
        self.value = value

    def __enter__(self):
        self.output.append(self.value)

    def __exit__(self, *exc_info):
        self.output.append(-self.value)

# A very basic example.  If this fails, we're in deep trouble.
def basic():
    return 1

basic.events = [(0, 'call'),
                (1, 'line'),
                (1, 'return')]

# Many of the tests below are tricky because they involve pass statements.
# If there is implicit control flow around a pass statement (in an except
# clause or else clause) under what conditions do you set a line number
# following that clause?


# The entire "while 0:" statement is optimized away.  No code
# exists for it, so the line numbers skip directly from "del x"
# to "x = 1".
def arigo_example():
    x = 1
    del x
    while 0:
        pass
    x = 1

arigo_example.events = [(0, 'call'),
                        (1, 'line'),
                        (2, 'line'),
                        (5, 'line'),
                        (5, 'return')]

# check that lines consisting of just one instruction get traced:
def one_instr_line():
    x = 1
    del x
    x = 1

one_instr_line.events = [(0, 'call'),
                         (1, 'line'),
                         (2, 'line'),
                         (3, 'line'),
                         (3, 'return')]

def no_pop_tops():      # 0
    x = 1               # 1
    for a in range(2):  # 2
        if a:           # 3
            x = 1       # 4
        else:           # 5
            x = 1       # 6

no_pop_tops.events = [(0, 'call'),
                      (1, 'line'),
                      (2, 'line'),
                      (3, 'line'),
                      (6, 'line'),
                      (2, 'line'),
                      (3, 'line'),
                      (4, 'line'),
                      (2, 'line'),
                      (2, 'return')]

def no_pop_blocks():
    y = 1
    while not y:
        bla
    x = 1

no_pop_blocks.events = [(0, 'call'),
                        (1, 'line'),
                        (2, 'line'),
                        (4, 'line'),
                        (4, 'return')]

def called(): # line -3
    x = 1

def call():   # line 0
    called()

call.events = [(0, 'call'),
               (1, 'line'),
               (-3, 'call'),
               (-2, 'line'),
               (-2, 'return'),
               (1, 'return')]

def raises():
    raise Exception

def test_raise():
    try:
        raises()
    except Exception as exc:
        x = 1

test_raise.events = [(0, 'call'),
                     (1, 'line'),
                     (2, 'line'),
                     (-3, 'call'),
                     (-2, 'line'),
                     (-2, 'exception'),
                     (-2, 'return'),
                     (2, 'exception'),
                     (3, 'line'),
                     (4, 'line'),
                     (4, 'return')]

def _settrace_and_return(tracefunc):
    sys.settrace(tracefunc)
    sys._getframe().f_back.f_trace = tracefunc
def settrace_and_return(tracefunc):
    _settrace_and_return(tracefunc)

settrace_and_return.events = [(1, 'return')]

def _settrace_and_raise(tracefunc):
    sys.settrace(tracefunc)
    sys._getframe().f_back.f_trace = tracefunc
    raise RuntimeError
def settrace_and_raise(tracefunc):
    try:
        _settrace_and_raise(tracefunc)
    except RuntimeError as exc:
        pass

settrace_and_raise.events = [(2, 'exception'),
                             (3, 'line'),
                             (4, 'line'),
                             (4, 'return')]

# implicit return example
# This test is interesting because of the else: pass
# part of the code.  The code generate for the true
# part of the if contains a jump past the else branch.
# The compiler then generates an implicit "return None"
# Internally, the compiler visits the pass statement
# and stores its line number for use on the next instruction.
# The next instruction is the implicit return None.
def ireturn_example():
    a = 5
    b = 5
    if a == b:
        b = a+1
    else:
        pass

ireturn_example.events = [(0, 'call'),
                          (1, 'line'),
                          (2, 'line'),
                          (3, 'line'),
                          (4, 'line'),
                          (6, 'line'),
                          (6, 'return')]

# Tight loop with while(1) example (SF #765624)
def tightloop_example():
    items = range(0, 3)
    try:
        i = 0
        while 1:
            b = items[i]; i+=1
    except IndexError:
        pass

tightloop_example.events = [(0, 'call'),
                            (1, 'line'),
                            (2, 'line'),
                            (3, 'line'),
                            (4, 'line'),
                            (5, 'line'),
                            (5, 'line'),
                            (5, 'line'),
                            (5, 'line'),
                            (5, 'exception'),
                            (6, 'line'),
                            (7, 'line'),
                            (7, 'return')]

def tighterloop_example():
    items = range(1, 4)
    try:
        i = 0
        while 1: i = items[i]
    except IndexError:
        pass

tighterloop_example.events = [(0, 'call'),
                            (1, 'line'),
                            (2, 'line'),
                            (3, 'line'),
                            (4, 'line'),
                            (4, 'line'),
                            (4, 'line'),
                            (4, 'line'),
                            (4, 'exception'),
                            (5, 'line'),
                            (6, 'line'),
                            (6, 'return')]

def generator_function():
    try:
        yield True
        "continued"
    finally:
        "finally"
def generator_example():
    # any() will leave the generator before its end
    x = any(generator_function())

    # the following lines were not traced
    for x in range(10):
        y = x

generator_example.events = ([(0, 'call'),
                             (2, 'line'),
                             (-6, 'call'),
                             (-5, 'line'),
                             (-4, 'line'),
                             (-4, 'return'),
                             (-4, 'call'),
                             (-4, 'exception'),
                             (-1, 'line'),
                             (-1, 'return')] +
                            [(5, 'line'), (6, 'line')] * 10 +
                            [(5, 'line'), (5, 'return')])


class Tracer:
    def __init__(self):
        self.events = []
    def trace(self, frame, event, arg):
        self.events.append((frame.f_lineno, event))
        return self.trace
    def traceWithGenexp(self, frame, event, arg):
        (o for o in [1])
        self.events.append((frame.f_lineno, event))
        return self.trace

class TraceTestCase(unittest.TestCase):

    # Disable gc collection when tracing, otherwise the
    # deallocators may be traced as well.
    def setUp(self):
        self.using_gc = gc.isenabled()
        gc.disable()
        self.addCleanup(sys.settrace, sys.gettrace())

    def tearDown(self):
        if self.using_gc:
            gc.enable()

    def compare_events(self, line_offset, events, expected_events):
        events = [(l - line_offset, e) for (l, e) in events]
        if events != expected_events:
            self.fail(
                "events did not match expectation:\n" +
                "\n".join(difflib.ndiff([str(x) for x in expected_events],
                                        [str(x) for x in events])))

    def run_and_compare(self, func, events):
        tracer = Tracer()
        sys.settrace(tracer.trace)
        func()
        sys.settrace(None)
        self.compare_events(func.__code__.co_firstlineno,
                            tracer.events, events)

    def run_test(self, func):
        self.run_and_compare(func, func.events)

    def run_test2(self, func):
        tracer = Tracer()
        func(tracer.trace)
        sys.settrace(None)
        self.compare_events(func.__code__.co_firstlineno,
                            tracer.events, func.events)

    def test_set_and_retrieve_none(self):
        sys.settrace(None)
        assert sys.gettrace() is None

    def test_set_and_retrieve_func(self):
        def fn(*args):
            pass

        sys.settrace(fn)
        try:
            assert sys.gettrace() is fn
        finally:
            sys.settrace(None)

    def test_01_basic(self):
        self.run_test(basic)
    def test_02_arigo(self):
        self.run_test(arigo_example)
    def test_03_one_instr(self):
        self.run_test(one_instr_line)
    def test_04_no_pop_blocks(self):
        self.run_test(no_pop_blocks)
    def test_05_no_pop_tops(self):
        self.run_test(no_pop_tops)
    def test_06_call(self):
        self.run_test(call)
    def test_07_raise(self):
        self.run_test(test_raise)

    def test_08_settrace_and_return(self):
        self.run_test2(settrace_and_return)
    def test_09_settrace_and_raise(self):
        self.run_test2(settrace_and_raise)
    def test_10_ireturn(self):
        self.run_test(ireturn_example)
    def test_11_tightloop(self):
        self.run_test(tightloop_example)
    def test_12_tighterloop(self):
        self.run_test(tighterloop_example)

    def test_13_genexp(self):
        self.run_test(generator_example)
        # issue1265: if the trace function contains a generator,
        # and if the traced function contains another generator
        # that is not completely exhausted, the trace stopped.
        # Worse: the 'finally' clause was not invoked.
        tracer = Tracer()
        sys.settrace(tracer.traceWithGenexp)
        generator_example()
        sys.settrace(None)
        self.compare_events(generator_example.__code__.co_firstlineno,
                            tracer.events, generator_example.events)

    def test_14_onliner_if(self):
        def onliners():
            if True: x=False
            else: x=True
            return 0
        self.run_and_compare(
            onliners,
            [(0, 'call'),
             (1, 'line'),
             (3, 'line'),
             (3, 'return')])

    def test_15_loops(self):
        # issue1750076: "while" expression is skipped by debugger
        def for_example():
            for x in range(2):
                pass
        self.run_and_compare(
            for_example,
            [(0, 'call'),
             (1, 'line'),
             (2, 'line'),
             (1, 'line'),
             (2, 'line'),
             (1, 'line'),
             (1, 'return')])

        def while_example():
            # While expression should be traced on every loop
            x = 2
            while x > 0:
                x -= 1
        self.run_and_compare(
            while_example,
            [(0, 'call'),
             (2, 'line'),
             (3, 'line'),
             (4, 'line'),
             (3, 'line'),
             (4, 'line'),
             (3, 'line'),
             (3, 'return')])

    def test_16_blank_lines(self):
        namespace = {}
        exec("def f():\n" + "\n" * 256 + "    pass", namespace)
        self.run_and_compare(
            namespace["f"],
            [(0, 'call'),
             (257, 'line'),
             (257, 'return')])

    def test_17_none_f_trace(self):
        # Issue 20041: fix TypeError when f_trace is set to None.
        def func():
            sys._getframe().f_trace = None
            lineno = 2
        self.run_and_compare(func,
            [(0, 'call'),
             (1, 'line')])


class RaisingTraceFuncTestCase(unittest.TestCase):
    def setUp(self):
        self.addCleanup(sys.settrace, sys.gettrace())

    def trace(self, frame, event, arg):
        """A trace function that raises an exception in response to a
        specific trace event."""
        if event == self.raiseOnEvent:
            raise ValueError # just something that isn't RuntimeError
        else:
            return self.trace

    def f(self):
        """The function to trace; raises an exception if that's the case
        we're testing, so that the 'exception' trace event fires."""
        if self.raiseOnEvent == 'exception':
            x = 0
            y = 1/x
        else:
            return 1

    def run_test_for_event(self, event):
        """Tests that an exception raised in response to the given event is
        handled OK."""
        self.raiseOnEvent = event
        try:
            for i in range(sys.getrecursionlimit() + 1):
                sys.settrace(self.trace)
                try:
                    self.f()
                except ValueError:
                    pass
                else:
                    self.fail("exception not raised!")
        except RuntimeError:
            self.fail("recursion counter not reset")

    # Test the handling of exceptions raised by each kind of trace event.
    def test_call(self):
        self.run_test_for_event('call')
    def test_line(self):
        self.run_test_for_event('line')
    def test_return(self):
        self.run_test_for_event('return')
    def test_exception(self):
        self.run_test_for_event('exception')

    def test_trash_stack(self):
        def f():
            for i in range(5):
                print(i)  # line tracing will raise an exception at this line

        def g(frame, why, extra):
            if (why == 'line' and
                frame.f_lineno == f.__code__.co_firstlineno + 2):
                raise RuntimeError("i am crashing")
            return g

        sys.settrace(g)
        try:
            f()
        except RuntimeError:
            # the test is really that this doesn't segfault:
            import gc
            gc.collect()
        else:
            self.fail("exception not propagated")


    def test_exception_arguments(self):
        def f():
            x = 0
            # this should raise an error
            x.no_such_attr
        def g(frame, event, arg):
            if (event == 'exception'):
                type, exception, trace = arg
                self.assertIsInstance(exception, Exception)
            return g

        existing = sys.gettrace()
        try:
            sys.settrace(g)
            try:
                f()
            except AttributeError:
                # this is expected
                pass
        finally:
            sys.settrace(existing)


# 'Jump' tests: assigning to frame.f_lineno within a trace function
# moves the execution position - it's how debuggers implement a Jump
# command (aka. "Set next statement").

class JumpTracer:
    """Defines a trace function that jumps from one place to another."""

    def __init__(self, function, jumpFrom, jumpTo):
        self.function = function
        self.jumpFrom = jumpFrom
        self.jumpTo = jumpTo
        self.done = False

    def trace(self, frame, event, arg):
        if not self.done and frame.f_code == self.function.__code__:
            firstLine = frame.f_code.co_firstlineno
            if event == 'line' and frame.f_lineno == firstLine + self.jumpFrom:
                # Cope with non-integer self.jumpTo (because of
                # no_jump_to_non_integers below).
                try:
                    frame.f_lineno = firstLine + self.jumpTo
                except TypeError:
                    frame.f_lineno = self.jumpTo
                self.done = True
        return self.trace

# This verifies the line-numbers-must-be-integers rule.
def no_jump_to_non_integers(output):
    try:
        output.append(2)
    except ValueError as e:
        output.append('integer' in str(e))

# This verifies that you can't set f_lineno via _getframe or similar
# trickery.
def no_jump_without_trace_function():
    try:
        previous_frame = sys._getframe().f_back
        previous_frame.f_lineno = previous_frame.f_lineno
    except ValueError as e:
        # This is the exception we wanted; make sure the error message
        # talks about trace functions.
        if 'trace' not in str(e):
            raise
    else:
        # Something's wrong - the expected exception wasn't raised.
        raise AssertionError("Trace-function-less jump failed to fail")


class JumpTestCase(unittest.TestCase):
    def setUp(self):
        self.addCleanup(sys.settrace, sys.gettrace())
        sys.settrace(None)

    def compare_jump_output(self, expected, received):
        if received != expected:
            self.fail( "Outputs don't match:\n" +
                       "Expected: " + repr(expected) + "\n" +
                       "Received: " + repr(received))

    def run_test(self, func, jumpFrom, jumpTo, expected, error=None):
        tracer = JumpTracer(func, jumpFrom, jumpTo)
        sys.settrace(tracer.trace)
        output = []
        if error is None:
            func(output)
        else:
            with self.assertRaisesRegex(*error):
                func(output)
        sys.settrace(None)
        self.compare_jump_output(expected, output)

    def jump_test(jumpFrom, jumpTo, expected, error=None):
        """Decorator that creates a test that makes a jump
        from one place to another in the following code.
        """
        def decorator(func):
            @wraps(func)
            def test(self):
                # +1 to compensate a decorator line
                self.run_test(func, jumpFrom+1, jumpTo+1, expected, error)
            return test
        return decorator

    ## The first set of 'jump' tests are for things that are allowed:

    @jump_test(1, 3, [3])
    def test_jump_simple_forwards(output):
        output.append(1)
        output.append(2)
        output.append(3)

    @jump_test(2, 1, [1, 1, 2])
    def test_jump_simple_backwards(output):
        output.append(1)
        output.append(2)

    @jump_test(3, 5, [2, 5])
    def test_jump_out_of_block_forwards(output):
        for i in 1, 2:
            output.append(2)
            for j in [3]:  # Also tests jumping over a block
                output.append(4)
        output.append(5)

    @jump_test(6, 1, [1, 3, 5, 1, 3, 5, 6, 7])
    def test_jump_out_of_block_backwards(output):
        output.append(1)
        for i in [1]:
            output.append(3)
            for j in [2]:  # Also tests jumping over a block
                output.append(5)
            output.append(6)
        output.append(7)

    @jump_test(1, 2, [3])
    def test_jump_to_codeless_line(output):
        output.append(1)
        # Jumping to this line should skip to the next one.
        output.append(3)

    @jump_test(2, 2, [1, 2, 3])
    def test_jump_to_same_line(output):
        output.append(1)
        output.append(2)
        output.append(3)

    # Tests jumping within a finally block, and over one.
    @jump_test(4, 9, [2, 9])
    def test_jump_in_nested_finally(output):
        try:
            output.append(2)
        finally:
            output.append(4)
            try:
                output.append(6)
            finally:
                output.append(8)
            output.append(9)

    @jump_test(6, 7, [2, 7], (ZeroDivisionError, ''))
    def test_jump_in_nested_finally_2(output):
        try:
            output.append(2)
            1/0
            return
        finally:
            output.append(6)
            output.append(7)
        output.append(8)

    @jump_test(6, 11, [2, 11], (ZeroDivisionError, ''))
    def test_jump_in_nested_finally_3(output):
        try:
            output.append(2)
            1/0
            return
        finally:
            output.append(6)
            try:
                output.append(8)
            finally:
                output.append(10)
            output.append(11)
        output.append(12)

    @jump_test(3, 4, [1, 4])
    def test_jump_infinite_while_loop(output):
        output.append(1)
        while True:
            output.append(3)
        output.append(4)

    @jump_test(2, 3, [1, 3])
    def test_jump_forwards_out_of_with_block(output):
        with tracecontext(output, 1):
            output.append(2)
        output.append(3)

    @jump_test(3, 1, [1, 2, 1, 2, 3, -2])
    def test_jump_backwards_out_of_with_block(output):
        output.append(1)
        with tracecontext(output, 2):
            output.append(3)

    @jump_test(2, 5, [5])
    def test_jump_forwards_out_of_try_finally_block(output):
        try:
            output.append(2)
        finally:
            output.append(4)
        output.append(5)

    @jump_test(3, 1, [1, 1, 3, 5])
    def test_jump_backwards_out_of_try_finally_block(output):
        output.append(1)
        try:
            output.append(3)
        finally:
            output.append(5)

    @jump_test(2, 6, [6])
    def test_jump_forwards_out_of_try_except_block(output):
        try:
            output.append(2)
        except:
            output.append(4)
            raise
        output.append(6)

    @jump_test(3, 1, [1, 1, 3])
    def test_jump_backwards_out_of_try_except_block(output):
        output.append(1)
        try:
            output.append(3)
        except:
            output.append(5)
            raise

    @jump_test(5, 7, [4, 7, 8])
    def test_jump_between_except_blocks(output):
        try:
            1/0
        except ZeroDivisionError:
            output.append(4)
            output.append(5)
        except FloatingPointError:
            output.append(7)
        output.append(8)

    @jump_test(5, 6, [4, 6, 7])
    def test_jump_within_except_block(output):
        try:
            1/0
        except:
            output.append(4)
            output.append(5)
            output.append(6)
        output.append(7)

    @jump_test(2, 4, [1, 4, 5, -4])
    def test_jump_across_with(output):
        output.append(1)
        with tracecontext(output, 2):
            output.append(3)
        with tracecontext(output, 4):
            output.append(5)

    @jump_test(8, 11, [1, 3, 5, 11, 12])
    def test_jump_out_of_complex_nested_blocks(output):
        output.append(1)
        for i in [1]:
            output.append(3)
            for j in [1, 2]:
                output.append(5)
                try:
                    for k in [1, 2]:
                        output.append(8)
                finally:
                    output.append(10)
            output.append(11)
        output.append(12)

    @jump_test(3, 5, [1, 2, 5])
    def test_jump_out_of_with_assignment(output):
        output.append(1)
        with tracecontext(output, 2) \
                as x:
            output.append(4)
        output.append(5)

    @jump_test(3, 6, [1, 6, 8, 9])
    def test_jump_over_return_in_try_finally_block(output):
        output.append(1)
        try:
            output.append(3)
            if not output: # always false
                return
            output.append(6)
        finally:
            output.append(8)
        output.append(9)

    @jump_test(5, 8, [1, 3, 8, 10, 11, 13])
    def test_jump_over_break_in_try_finally_block(output):
        output.append(1)
        while True:
            output.append(3)
            try:
                output.append(5)
                if not output: # always false
                    break
                output.append(8)
            finally:
                output.append(10)
            output.append(11)
            break
        output.append(13)

    @jump_test(1, 7, [7, 8])
    def test_jump_over_for_block_before_else(output):
        output.append(1)
        if not output:  # always false
            for i in [3]:
                output.append(4)
        else:
            output.append(6)
            output.append(7)
        output.append(8)

    # The second set of 'jump' tests are for things that are not allowed:

    @jump_test(2, 3, [1], (ValueError, 'after'))
    def test_no_jump_too_far_forwards(output):
        output.append(1)
        output.append(2)

    @jump_test(2, -2, [1], (ValueError, 'before'))
    def test_no_jump_too_far_backwards(output):
        output.append(1)
        output.append(2)

    # Test each kind of 'except' line.
    @jump_test(2, 3, [4], (ValueError, 'except'))
    def test_no_jump_to_except_1(output):
        try:
            output.append(2)
        except:
            output.append(4)
            raise

    @jump_test(2, 3, [4], (ValueError, 'except'))
    def test_no_jump_to_except_2(output):
        try:
            output.append(2)
        except ValueError:
            output.append(4)
            raise

    @jump_test(2, 3, [4], (ValueError, 'except'))
    def test_no_jump_to_except_3(output):
        try:
            output.append(2)
        except ValueError as e:
            output.append(4)
            raise e

    @jump_test(2, 3, [4], (ValueError, 'except'))
    def test_no_jump_to_except_4(output):
        try:
            output.append(2)
        except (ValueError, RuntimeError) as e:
            output.append(4)
            raise e

    @jump_test(1, 3, [], (ValueError, 'into'))
    def test_no_jump_forwards_into_for_block(output):
        output.append(1)
        for i in 1, 2:
            output.append(3)

    @jump_test(3, 2, [2, 2], (ValueError, 'into'))
    def test_no_jump_backwards_into_for_block(output):
        for i in 1, 2:
            output.append(2)
        output.append(3)

    @jump_test(2, 4, [], (ValueError, 'into'))
    def test_no_jump_forwards_into_while_block(output):
        i = 1
        output.append(2)
        while i <= 2:
            output.append(4)
            i += 1

    @jump_test(5, 3, [3, 3], (ValueError, 'into'))
    def test_no_jump_backwards_into_while_block(output):
        i = 1
        while i <= 2:
            output.append(3)
            i += 1
        output.append(5)

    @jump_test(1, 3, [], (ValueError, 'into'))
    def test_no_jump_forwards_into_with_block(output):
        output.append(1)
        with tracecontext(output, 2):
            output.append(3)

    @jump_test(3, 2, [1, 2, -1], (ValueError, 'into'))
    def test_no_jump_backwards_into_with_block(output):
        with tracecontext(output, 1):
            output.append(2)
        output.append(3)

    @jump_test(1, 3, [], (ValueError, 'into'))
    def test_no_jump_forwards_into_try_finally_block(output):
        output.append(1)
        try:
            output.append(3)
        finally:
            output.append(5)

    @jump_test(5, 2, [2, 4], (ValueError, 'into'))
    def test_no_jump_backwards_into_try_finally_block(output):
        try:
            output.append(2)
        finally:
            output.append(4)
        output.append(5)

    @jump_test(1, 3, [], (ValueError, 'into'))
    def test_no_jump_forwards_into_try_except_block(output):
        output.append(1)
        try:
            output.append(3)
        except:
            output.append(5)
            raise

    @jump_test(6, 2, [2], (ValueError, 'into'))
    def test_no_jump_backwards_into_try_except_block(output):
        try:
            output.append(2)
        except:
            output.append(4)
            raise
        output.append(6)

    # 'except' with a variable creates an implicit finally block
    @jump_test(5, 7, [4], (ValueError, 'into'))
    def test_no_jump_between_except_blocks_2(output):
        try:
            1/0
        except ZeroDivisionError:
            output.append(4)
            output.append(5)
        except FloatingPointError as e:
            output.append(7)
        output.append(8)

    @jump_test(3, 6, [2, 5, 6], (ValueError, 'finally'))
    def test_no_jump_into_finally_block(output):
        try:
            output.append(2)
            output.append(3)
        finally:  # still executed if the jump is failed
            output.append(5)
            output.append(6)
        output.append(7)

    @jump_test(1, 5, [], (ValueError, 'finally'))
    def test_no_jump_into_finally_block_2(output):
        output.append(1)
        try:
            output.append(3)
        finally:
            output.append(5)

    @jump_test(5, 1, [1, 3], (ValueError, 'finally'))
    def test_no_jump_out_of_finally_block(output):
        output.append(1)
        try:
            output.append(3)
        finally:
            output.append(5)

    @jump_test(3, 5, [1, 2, -2], (ValueError, 'into'))
    def test_no_jump_between_with_blocks(output):
        output.append(1)
        with tracecontext(output, 2):
            output.append(3)
        with tracecontext(output, 4):
            output.append(5)

    @jump_test(7, 4, [1, 6], (ValueError, 'into'))
    def test_no_jump_into_for_block_before_else(output):
        output.append(1)
        if not output:  # always false
            for i in [3]:
                output.append(4)
        else:
            output.append(6)
            output.append(7)
        output.append(8)

    def test_no_jump_to_non_integers(self):
        self.run_test(no_jump_to_non_integers, 2, "Spam", [True])

    def test_no_jump_without_trace_function(self):
        # Must set sys.settrace(None) in setUp(), else condition is not
        # triggered.
        no_jump_without_trace_function()

    def test_large_function(self):
        d = {}
        exec("""def f(output):        # line 0
            x = 0                     # line 1
            y = 1                     # line 2
            '''                       # line 3
            %s                        # lines 4-1004
            '''                       # line 1005
            x += 1                    # line 1006
            output.append(x)          # line 1007
            return""" % ('\n' * 1000,), d)
        f = d['f']
        self.run_test(f, 2, 1007, [0])

    def test_jump_to_firstlineno(self):
        # This tests that PDB can jump back to the first line in a
        # file.  See issue #1689458.  It can only be triggered in a
        # function call if the function is defined on a single line.
        code = compile("""
# Comments don't count.
output.append(2)  # firstlineno is here.
output.append(3)
output.append(4)
""", "<fake module>", "exec")
        class fake_function:
            __code__ = code
        tracer = JumpTracer(fake_function, 2, 0)
        sys.settrace(tracer.trace)
        namespace = {"output": []}
        exec(code, namespace)
        sys.settrace(None)
        self.compare_jump_output([2, 3, 2, 3, 4], namespace["output"])


if __name__ == "__main__":
    unittest.main()
