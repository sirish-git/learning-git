import os

# find the values from file and find average
count = 3
with open('test_input.txt', 'r') as finp:
  cnt = 0
  val = 0
  for line in finp:
    line = line.strip('\n')
    list = line.split(' ')
    if 'us' in list:
      id = list.index('us')-1
      print(list), 'id:', id
      if cnt < count:
        cnt += 1
        val += float(list[id])
        print 'val:', val
	if cnt == count:
          avg = val/count
  	  print 'avg:', avg
          cnt = 0
	  val = 0
     
      
