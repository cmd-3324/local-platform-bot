
# import csv

# data = [
#     ['Name', 'Age', 'Grade', 'City'],
#     ['Alice', 20, 85, 'New York'],
#     ['Bob', 22, 90, 'Boston'],
#     ['Charlie', 21, 88, 'Chicago'],
#     ['Diana', 23, 92, 'New York'],
#     ['Eve', 20, 78, 'Boston']
# ]
# path = "C:\\Users\\Rayan_Svc\\bot-python-sdk\\Files3\\"

# try:
#     with open('students.csv', 'w+', newline='') as file:
#         writer = csv.writer(file)
#         writer.writerows(data)
# except Exception as e:
#     print(e)
import csv
import pandas as pd
# Process without loading all into memory
# with open('huge_file.csv', 'r') as file:
#     reader = csv.DictReader(file)
    
#     total_grade = 0
#     count = 0
    
#     for row in reader:  # One row at a time
#         total_grade += int(row['Grade'])
#         count += 1
        
#         # Do something with each row
#         if int(row['Grade']) > 90:
#             print(f"Excellent: {row['Name']}")
    
#     print(f"Average: {total_grade/count}")
    
# Make a simple table of students
data = {
    'Name': ['Alice', 'Bob', 'Charlie'],
    'Age': [20, 22, 21],
    'Grade': [85, 90, 88]
}
prefix_path = "C:\\Users\\Rayan_Svc\\bot-python-sdk\\Files3\\"
df = pd.DataFrame(data)
# df.set_index("Name", inplace=True)
df.to_csv(f'{prefix_path}output.csv')
print(df.tail(1))
# print("File created: students.csv")