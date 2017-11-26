
COUNT_AVG = 3


names = ['first', 'second']
titles = ['name', 'title-1', 'title-2']


row = 1
col = 1
# create xl sheet
import xlsxwriter
workbook = xlsxwriter.Workbook('xl_report.xlsx')
# create a worksheet
worksheet = workbook.add_worksheet('report')
# define column width
worksheet.set_column(col, col, 20)
worksheet.set_column(col+1, col+2, 8)

# define format
format_bold = workbook.add_format(
 { 
#  'align': True,
  'bold': True,
  'border': 2,
  'font_size': 18,
 }
)
# write title list
worksheet.write(row, col, 'titles', format_bold)


# find the values from file and find average
g_cnt = 0
with open('test_input.txt', 'r') as finp:
  cnt = 0
  val = 0
  for line in finp:
    line = line.strip('\n')
    list = line.split(' ')
    if 'us' in list:
      id = list.index('us')-1
      print(list), 'id:', id
      if cnt < COUNT_AVG:
        cnt += 1
        val += float(list[id])
        print 'val:', val
	if cnt == COUNT_AVG:
          avg = val/COUNT_AVG
  	  print 'g_cnt:', g_cnt, ' avg:', avg
          g_cnt += 1
          cnt = 0
	  val = 0
     
      
workbook.close()
