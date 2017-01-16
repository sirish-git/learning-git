
# This is a python comment

# print in python: prints on new lines
print "Hello World"
print 'Same Hello world with single quotes'
# prints in same line by using comma
print "print in",
print 'same line'
# use escape sequence 
print 'print single \' quote with backspace'
print "print single ' quote within double quotes"
print 'print backspace \\ using backspace character'
# python puts space
i=50
print 'python space: i value is',i


# use format to print
name = 'bond' # "" and '' are same in python string usage
age = 25
print '{0} is {1} years old'.format(name, age)
# use format without index
print '{} is {} years old: without index'.format(name, age)
# use format for a different format specifier
print '{0:.3f}'.format(1.0/3)

# multiple logical statements in one physical line
i = 5
print 'i value is', i
i=10; print 'single line: i value is', i

# + operator
a = 'i'
b = 'am'
s = a + b
print 'i+am=', s

# * operator
a = 'am'
print 'am*3=', a*3

# indentation
print 'group of statements with same indentation forms a block'
print 'python suggested indentation is 4 spaces'
print 'unnecessary indentation gives error'

# if: observe colon ':' after each if condition including else
# there is no switch operator in python
val = 1
if val == 1:
    # new block starts
    print 'start of block'
    print 'observe colon : after each if condition'
    val = 2
    print 'end of block'
    # end of block

if val == 1:
    #true block
    val = 3
elif val == 3:
    #else if block
    val = 4
else:
    #new block
    print 'else block'

# while
# a while can have an optional else clause

# for 
# a for can have an optional else clause
# range function generates sequence of numbers with step count 1
for i in range(0,5):
 print "iteration cnt:", i
# step count 2
for i in range(0,5,2):
    print 'step 2: iteration cnt:', i

# break and continue operators used as C language

# functions
# functions are defined using the def keyword
def fn_hello():
 # block starts
 print 'hello from fn_hello'

print 'call fn_hello:'
fn_hello()

# global
# global keyword should be used to assign value to a global variable inside a function
val = 25
def fn_global():
 #global keyword to reference global variable
 global val
 print 'inside fn: val is', val
 val = 50
 print 'inside fn: val is', val

fn_global()
print 'outside fn: val is', val


# keyword arguments

# variable number of arguments

# documentation strings
def find_max_doc(x, y):
# docstring of the function
 '''fn description: finds max value of 2 numbers '''
 if x > y:
  print 'max value is',x
 else:
  print 'max value is',y
find_max_doc(2,3)
print find_max_doc.__doc__


# modules
# import module
# print args
import sys
print 'command line args'
for i in sys.argv:
#prints cmd arg strings, not numbers
 print i

# import my test module
import test_module
test_module.fn_module()
print 'value from module', test_module.val_mod

# import functions, variables from test module
from test_module import fn_module, val_mod
fn_module()
print 'value from module', val_mod

# dir function to list the fn's, classes, variables part of a module

# packages

# data structures










