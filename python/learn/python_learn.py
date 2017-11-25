
# interpreter mode
print 'enter interpreter mode by typing python on terminal'
print 'exit interpreter mode by typing ctrl+d\n'


# Naming convetions:
'''
 - Class names start with an uppercase letter
 - Starting an identifier with a single leading underscore indicates that the identifier is private
 - Starting an identifier with two leading underscores indicates a strongly private identifier
 - If the identifier also ends with two trailing underscores, the identifier is a language-defined special name 
'''


# Python keywords
'''
 and		exec		not
 assert		finally		or
 break		for		pass
 class		from		print
 continue	global		raise
 def		if		return
 del		import		try
 elif		in		while
 else		is		with
 except		lambda		yield
'''

# Python membership operators
'''
Python’s membership operators test for membership in a sequence, such as strings, lists, or tuples. There are two membership operators
'''
# in
'''
Evaluates to true if it finds a variable in the specified sequence and false otherwise.
'''
# example
ls = [1, 'test', 4, 9]
'test' in ls
4 in ls

# not in
'''
Evaluates to true if it does not finds a variable in the specified sequence and false otherwise.
'''

# Python Identity Operators
'''
Identity operators compare the memory locations of two objects. There are two Identity operators explained below
'''
# is
'''
Evaluates to true if the variables on either side of the operator point to the same object and false otherwise.
'''
# example
x=2; y=2
x is y

# is not
'''
Evaluates to false if the variables on either side of the operator point to the same object and true otherwise.
'''


# built-in functions 
# dir([object]):
'''
Without arguments, return the list of names in the current local scope. With an argument, attempt to return a list of valid attributes for that object.
'''

# enumerate(iterable, start=0)
'''
Return an enumerate object. iterable must be a sequence,
'''
# example
lst = [1, 'hi', 4]
for idx, ls in enumerate(lst):
 print (idx, ls)

# help([object])
'''
Invoke the built-in help system. If no argument is given, the interactive help system starts on the interpreter console. If the argument is a string, then the string is looked up as the name of a module, function, class, method, keyword, or documentation topic, and a help page is printed on the console.
'''

# id(object)
'''
Return the “identity” of an object. This is an integer which is guaranteed to be unique and constant for this object during its lifetime.
'''

# input([prompt])
'''
If the prompt argument is present, it is written to standard output without a trailing newline. The function then reads a line from input, converts it to a string (stripping a trailing newline), and returns that. When EOF is read, EOFError is raised.
'''

# open
'''
open(file, mode=’r’, buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None)
'''

# sorted
'''
sorted(iterable[, key][, reverse])
Return a new sorted list from the items in iterable.
'''


# multiline comment
'''
This is multiline comment
using triple quotes
'''

# Multi-Line Statements
'''
Python allow the use of the line continuation character (\) to denote that the line should continue. For example 

total = item_one + \
        item_two + \
        item_three

Statements contained within the [], {}, or () brackets do not need to use the line continuation character. For example 

days = ['Monday', 'Tuesday', 'Wednesday',
        'Thursday', 'Friday']
'''


# This is a python comment

print 
# print in python: prints on new lines
print "Hello World"
print 'Same Hello world with single quotes'
print 'python auto inserts new line'
# prints in same line by using comma
print "Can avoid default newline using",
print 'the comma operator'
print '\\n character to put extra new line\n'
# use escape sequence 
print 'print single \' quote with backspace'
print "print single ' quote within double quotes"
print 'print backspace \\ using backspace character'
print "'' and \"\" quotes usage are same with strings" # "" and '' are same in python string usage
# python puts space
i=50
print 'python space: i value is',i
# strings can be added in print also
str1 = 'in print also'
print 'strings ' + 'can be added ' + str1
# print as function
val = 3
print ("%10d" %(val))
# print - 10 times
print ("-" * 10


# use format to print
name = 'bond' 
age = 25
print '{0} is {1} years old'.format(name, age)
# use format without index
print '{} is {} years old: without index'.format(name, age)
# use format for a different format specifier
print '{0:.3f}'.format(1.0/3)
print


# multiple logical statements in one physical line
i = 5
print 'i value is', i
i=10; print 'multiple statements in single line using semicolon; i value is', i
print



# Python Strings
'''
Python allows for either pairs of single or double quotes. Subsets of strings can be taken using the slice operator ([ ] and [:] ) with indexes starting at 0 in the beginning of the string and working their way from -1 at the end.

The plus (+) sign is the string concatenation operator and the asterisk (*) is the repetition operator
'''
#examples
str = 'Hello World!'

print str          # Prints complete string
print str[0]       # Prints first character of the string
print str[2:5]     # Prints characters starting from 3rd to 5th
print str[2:]      # Prints string starting from 3rd character
print str * 2      # Prints string two times
print str + "TEST" # Prints concatenated string
print

# + operator
a = 'i'
b = 'am'
s = a + b
print '+ operator on strings concatenates the result'
print 'i+am=', s
print

# concat strings using format
str2 = 'strings'
str3 = 'can be added'
str4 = '{} {} using format'.format(str2, str3)
print str4

# * operator
a = 'am'
print 'am*3=', a*3
print

# Unicode String
'''
Normal strings in Python are stored internally as 8-bit ASCII, while Unicode strings are stored as 16-bit Unicode. This allows for a more varied set of characters, including special characters from most languages in the world.
'''
#examples
print u'Hello, world!\n'



# Python Lists
'''
A list contains items separated by commas and enclosed within square brackets ([]). To some extent, lists are similar to arrays in C. One difference between them is that all the items belonging to a list can be of different data type.
'''
#examples
list = [ 'abcd', 786 , 2.23, 'john', 70.2 ]
tinylist = [123, 'john']

print list          # Prints complete list
print list[0]       # Prints first element of the list
print list[1:3]     # Prints elements starting from 2nd till 3rd 
print list[2:]      # Prints elements starting from 3rd element
print tinylist * 2  # Prints list two times
print list + tinylist # Prints concatenated lists
print

# Delete List Elements
list1 = ['physics', 'chemistry', 1997, 2000];

print list1
del list1[2];
print "After deleting value at index 2 : "
print list1
print

# Built-in List Functions & Methods:
#funcitons
'''
len(list), cmp(list), max(list)
'''
#methods
'''
list.append(obj), list.extern(obj)
'''



# Python Tuples
'''
A tuple is another sequence data type that is similar to the list. tuples are enclosed within parentheses. 
The main differences between lists and tuples are: Lists are enclosed in brackets ( [ ] ) and their elements and size can be changed, while tuples are enclosed in parentheses ( ( ) ) and cannot be updated. Tuples can be thought of as read-only lists
'''
#examples
tuple = ( 'abcd', 786 , 2.23, 'john', 70.2  )
tinytuple = (123, 'john')

print tuple           # Prints complete list
print tuple[0]        # Prints first element of the list
print tuple[1:3]      # Prints elements starting from 2nd till 3rd 
print tuple[2:]       # Prints elements starting from 3rd element
print tinytuple * 2   # Prints list two times
print tuple + tinytuple # Prints concatenated lists



# Python Dictionary
'''
Python's dictionaries are kind of hash table type. A dictionary key can be almost any Python type, but are usually numbers or strings. Values, on the other hand, can be any arbitrary Python object.
Dictionaries are enclosed by curly braces ({ }) and values can be assigned and accessed using square braces ([]).
'''
#examples
dict = {}
dict['one'] = "This is one"
dict[2]     = "This is two"

tinydict = {'name': 'john','code':6734, 'dept': 'sales'}

print dict['one']       # Prints value for 'one' key
print dict[2]           # Prints value for 2 key
print tinydict          # Prints complete dictionary
print tinydict.keys()   # Prints all the keys
print tinydict.values() # Prints all the values

# loop for dictionary
for key, value in dict.items():
  print key, value

#built-in methods
'''
dict.keys(), dict.items()
'''


# Data Type Conversion
'''
To convert between types, you simply use the type name as a function.
examples:
int(x [,base]), tuple(s), dict(d)
'''


# indentation
print 'group of statements with same indentation forms a block'
print 'python suggested indentation is 4 spaces'
print 'unnecessary indentation gives error'
print ''


# if
# observe colon ':' after each if condition including else
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
print ''


# while
# needs to use : after condition
# a while can have an optional else clause
test = 1
while test == 1:
    print 'While condition requires colon :'
    print 'While can have an optional else clause'
    test+=1
print ''


# for 
# a for can have an optional else clause
# range function generates sequence of numbers
'''
syntax of range: range(start,stop,step)
start is optional, if start is not specified starts from 0
step is optional, default step is 1
'''
for i in range(0,5):
 print "iteration cnt:", i
# step count 2
for i in range(0,5,2):
    print 'step 2: iteration cnt:', i
print ''

# range function generates sequence of numbers range(start, end, offset)
print "range syntax"
range(1,5,2)

# break and continue operators used as C language
print 'break and continue operator used as in C\n'



# functions
# functions are defined using the def keyword
def fn_hello():
 # block starts
 print 'hello from fn_hello'

print 'call fn_hello:'
fn_hello()


# main function
print 'python does not require a main function to be created, it is better to create for clarity'
print 'If every python file can have a function/main call'
print 'but when this file imported as module these function calls also gets executed'
print 'to avoid unnecessary execution of function calls in imported module we can create conditional function calls with __name__'
# __name__ example
def fn_name_example():
 print 'welcome to function __name__ example'

if __name__ == "__main__":
 fn_name_example()
 print 'name is set to __main__ when this file is directly executed, executed from imported file it is not set'
print ''


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


# function call by reference vs value

# keyword arguments

# default arguments

# variable number of arguments

# the anonymous functions
'''
using lambda keyword
'''


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
'''
A module allows you to logically organize your Python code, to reuse a number of functions in other programs . 
Simply, a module is a file consisting of Python code. A module can define functions, classes and variables. A module can also include runnable code.
'''
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


# dir function
'''
The dir() built-in function returns a sorted list of strings containing the names defined by a module.
'''
#examples
print 'sorted list of strings of names defined by test_module\n'
content = dir(test_module)
print content



# packages
'''
A package is a hierarchical file directory structure that defines a single Python application environment that consists of modules and subpackages
Packages are just folders of modules with a special init.py file that indicates to
Python that this folder is special because it contains Python modules
'''
#example
'''
To make all of your functions available when you've imported a directory (ex_dir) as a package, you need to put explicit import statements in __init__.py as follows
Then we can directly import the package/directory name (ex_dir) instead of individual modules
import ex_dir

'''




# Object oriented programming (oop)
'''
class attributes (fields and methods):
Variables that belong to an object or class are referred to as fields. Objects can also have functionality by using functions that belong to a class. Such functions are called methods of the class. 
 Collectively, the fields and methods can be referred to as the attributes of that class

Fields are of two types - they can belong to each instance/object of the class or they can belong to the class itself. They are called instance variables and class variables respectively.
'''

'''
self:
Class methods have only one specific difference from ordinary functions , they must have an extra first name that has to be added to the beginning of the parameter list, but you do not give a value for this parameter when you call the method, Python will provide it. This particular variable refers to the object itself, and by convention, it is given the name self .

We can use any name other than self, but better to use self.
The self in Python is equivalent to the this pointer in C++
'''
print

class Person:
  def say_hi(self):
    print('Hello, welcome to class and oop')

p = Person()
p.say_hi()
print

'''
__init__
The init method is run as soon as an object of a class is instantiated. The method is useful to do any initialization you want to do with your object. Notice the double underscores both at the beginning and at the end of the name
'''
class Person:
  def __init__(self, name):
# Note: self.name means that there is a field called "name" that is part of the object called "self" 
    self.name = name

  def say_hi(self):
    print 'Hello, my name is', self.name

p = Person('Swaroop')
p.say_hi()
print



# All class members (including the data members) are public and all the methods are virtual in Python.

# example: class fields/methods, instance/object fields/methods

class Test_Class:

 # class variable/field (can be accessed using class or object)
 obj_cnt = 0

 # default constructor
 def __init__(self, name):
  Test_Class.obj_cnt += 1
  # object field (can be accessed using only objects)
  self.name = name
  self.val = 0
  print 'Welcome to Test_Class: Object name ', self
  print 'obj_cnt value: ', Test_Class.obj_cnt
  

 # object method (can be called using an object)
 def obj_fn(self, val):
  self.val += 1
  self.sum = self.val + val
  print 'Welcome to obj_fn: Object name ', self
  print 'obj_fn counter (object value): ', self.val
  print 'self.name: ', self.name, ', self.sum: ', self.sum


 # class method using a below token @classmethod (can be called using Class, can alsom be called using oject)
 @classmethod
 def cls_fn(cls):
  print 'Welcome to cls_fn (class function) created with @classmethod'
  print 'objects cnt: ', Test_Class.obj_cnt
  # can not access any object variables
  # print 'val: ', cls.val


 # static method using a below token @staticmethod (like a normal function does not take object, class as 1st arguments)
 @staticmethod
 def static_fn():
  print 'Welcome to static_fn (static function) created with @staticmethod'
  #print 'objects cnt: ', Test_Class.obj_cnt


# create an object
obj_1 = Test_Class('sirish')
# call object function
obj_1.obj_fn(24)
# call class function with object
obj_1.cls_fn()
# call class function using class name
Test_Class.cls_fn()
# call static function using object
obj_1.static_fn()
# call static function using class
Test_Class.static_fn()

print
# second object
obj_2 = Test_Class('kumar')
obj_2.obj_fn(99)
obj_2.cls_fn()
Test_Class.cls_fn()
Test_Class.static_fn()

print



# File I/O
# Reading Keyboard Input
'''
Python provides two built-in functions to read a line of text from standard input, which by default comes from the keyboard. These functions are 

raw_input

input
'''

# The input Function
'''
The input([prompt]) function is equivalent to raw_input, except that it assumes the input is a valid Python expression and returns the evaluated result to you.
'''
val = open("enter value: ")
print val

# The raw_input Function: obsolete in python 3.x onwards
'''
The raw_input([prompt]) function reads one line from standard input and returns it as a string (removing the trailing newline).
'''

# Opening and Closing Files

# The open Function
'''
Before you can read or write a file, you have to open it using Python's built-in open() function. This function creates a file object, which would be utilized to call other support methods associated with it.

Syntax
file object = open(file_name [, access_mode][, buffering])
'''

# The file Object Attributes
'''
Once a file is opened and you have one file object, you can get various information related to that file.

Here is a list of all attributes related to file object:

Attribute	Description
file.closed	Returns true if file is closed, false otherwise.
file.mode	Returns access mode with which file was opened.
file.name	Returns name of the file.
file.softspace	Returns false if space explicitly required with print, true otherwise.
'''

#example
fo = open("foo.txt", "wb")
print "Name of the file: ", fo.name
print "Closed or not : ", fo.closed
print "Opening mode : ", fo.mode
print "Softspace flag : ", fo.softspace

# Reading and Writing Files
'''
use read() and write() methods to read and write files
'''
fo.write( "Python is a great language.\nYeah its great!!\n");

# The close() Method
fo.close()

# File Positions
'''
The tell() method tells you the current position within the file;
The seek(offset[, from]) method changes the current file position.
'''

# Renaming and Deleting Files
'''
rename, remove methods
'''

# Directories in Python
'''
 The os module has several methods that help you create, remove, and change directories.
'''
# The mkdir() Method
'''
You can use the mkdir() method of the os module to create directories in the current directory.
'''
#example
#os.mkdir("newdir")

# The chdir() Method
'''
You can use the chdir() method to change the current directory.
'''

# The rmdir() Method



# Exceptions Handling
'''
Python provides two very important features to handle any unexpected error in your Python programs and to add debugging capabilities
Exception handling
Assertions
'''

# Assertions
'''
An assertion is a sanity-check that you can turn on or turn off when you are done with your testing of the program.
'''

# Exceptions
'''
An exception is an event, which occurs during the execution of a program that disrupts the normal flow of the program's instructions. In general, when a Python script encounters a situation that it cannot cope with, it raises an exception. An exception is a Python object that represents an error.
'''
# Handling exception
'''
you can defend your program by placing the suspicious code in a try: block. After the try: block, include an except: statement, followed by a block of code which handles the problem as elegantly as possible.

try:
   You do your operations here;
   ......................
except ExceptionI:
   If there is ExceptionI, then execute this block.
except ExceptionII:
   If there is ExceptionII, then execute this block.
   ......................
else:
   If there is no exception then execute this block. 
'''
# example
try:
  fo = open("for.txt", "rb")
except:
  print 'exception error: file opening error\n'


#  Try  Finally
'''
Suppose you are reading a file in your program. How do you ensure that the file object
is closed properly whether or not an exception was raised? This can be done using
the finally block.

'''

# The with statement
'''
Acquiring a resource in the try block and subsequently releasing the resource in the
finally block is a common pattern. Hence, there is also a with statement that
enables this to be done in a clean manner:

with open("poem.txt") as f:
 for line in f:
 print line,
'''




