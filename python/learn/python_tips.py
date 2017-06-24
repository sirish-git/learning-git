
# python useful tips


# In-Place Swapping Of Two Numbers.
'''
Python provides an intuitive way to do assignments and swapping in one line.
The assignment on the right seeds a new tuple. While the left one instantly unpacks that (unreferenced) tuple to the names <a> and <b>.
'''
x, y = 10, 20
print(x, y)
 
x, y = y, x
print(x, y),'\n'


# Storing Elements Of A List Into New Variables.
'''
We can use a list to initialize a no. of variables. While unpacking the list, the count of variables should not exceed the no. of elements in the list.
'''
testList = [1,2,3]
x, y, z = testList
 
print(x, y, z),'\n'



# Use Of Ternary Operator For Conditional Assignment.
'''
Ternary operators are a shortcut for an if-else statement and also known as conditional operators.

Syntax:
[on_true] if [expression] else [on_false]
'''

x = 10 if (y == 9) else 20
print x,'\n'



# List comprehension
'''
We can even use a ternary operator with the list comprehension.
'''
auto_list = [m**2 if m > 5 else m**3 for m in range(10)]
print "auto_list: \n", auto_list,'\n'



# Dictionary/Set Comprehensions
'''
Like we use list comprehensions, we can also use dictionary/set comprehensions. They are simple to use and just as effective.
'''
testDict = {i: i * i for i in xrange(10)} 
testSet = {i * 2 for i in xrange(10)}
 
print 'testSet ',(testSet)
print 'testDict ',(testDict),'\n'



# Work With Multi-Line Strings
'''
The basic approach is to use backslashes which derive itself from C language.
'''

multiStr = "multi row using backspace \
operator"
print(multiStr)

'''
One more trick is to use the triple quotes.
'''
multiStr = """multi row using  
triple quotes"""
print(multiStr)

'''
The common issue with the above methods is the lack of proper indentation. If we try to indent, it will insert whitespaces in the string.
So the final solution is to split the string into multi lines and enclose the entire string in parenthesis.
'''
multiStr= ("multi row using "
"double quotes "
"enclosed in paranthesis")
print multiStr,'\n'



# Print The File Path Of Imported Modules
import test_module
print test_module,'\n'



# Use Interactive _ (underscore) Operator
'''
In the Python console, whenever we test an expression or call a function, the result dispatches to a temporary name, _ (an underscore).
'''


# Setup File Sharing



# Inspect An Object In Python
'''
We can inspect objects in Python by calling the dir() method.
'''
test = [1, 3, 5, 7]
print( dir(test) ),'\n'



# Simplify If Statement
'''
To verify multiple values, we can do in the following manner.
if m in [1,3,5,7]: instead of if m==1 or m==3 or m==5 or m==7:
'''



# Reverse A List Using Slicing
test = [1,2,3,4]
rev = test[::-1]
print test
print rev,'\n'



# Using Enumerate() Function
'''
The enumerate() function adds a counter to an iterable object. An iterable is an object that has a __iter__ method which returns an iterator. It can accept sequential indexes starting from zero. And raises an IndexError when the indexes are no longer valid.
'''
subjects = ('Python', 'Coding', 'Tips')
 
for i, subject in enumerate(subjects):
    print(i, subject)

print
for subject in enumerate(subjects):
 print subject

print
for subject in subjects:
 print subject



# Use Of Enums In Python
class Shapes:
	Circle, Square, Triangle, Quadrangle = range(4)
 
print
print(Shapes.Circle)
print(Shapes.Square)
print(Shapes.Triangle)
print(Shapes.Quadrangle),'\n'




# Return Multiple Values From Functions
def x():
	return 1, 2, 3, 4
 
a, b, c, d = x()
 
print(a, b, c, d),'\n'




# Unpack Function Arguments Using Splat Operator
'''
The splat operator offers an artistic way to unpack arguments lists.
'''
def test(x, y, z):
	print(x, y, z)
 
testDict = {'x': 1, 'y': 2, 'z': 3} 
testList = [10, 20, 30]
 
test(*testDict)
test(**testDict)
test(*testList)








