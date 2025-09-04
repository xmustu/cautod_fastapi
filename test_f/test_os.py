import os 
DIRECTORY = os.getenv("DIRECTORY")
dir = DIRECTORY
print(dir)
print(DIRECTORY)


print(os.path.dirname(os.path.abspath(__file__)))