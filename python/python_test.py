
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
