

val_mod = 10

def fn_module():
 print 'print in fn_module'
 print 'inside fn_module: val_mod', val_mod


# __name__ example
def fn_name_example_main():
 print 'welcome to function __name__ main example'

if __name__ == "__main__":
 fn_name_example_main()
 print 'name is set to __main__ when this file is directly executed, executed from imported file it is not set'
print ''


