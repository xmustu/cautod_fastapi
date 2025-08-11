import subprocess

def run_subprocess_with_realtime_output(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
    while True:
        output = process.stdout.readline().decode('utf-8')
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip())
    return process.poll()

# 示例调用
command = [r"C:\Users\dell\anaconda3\envs\sld\python.exe", r"C:\Users\dell\Projects\CAutoD\wenjian\sldwks.py"]
run_subprocess_with_realtime_output(command)