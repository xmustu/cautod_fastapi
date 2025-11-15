## Broker settings.
# broker_url = 'pyamqp://admin:admin@localhost//'
## Using the database to store task state and results. or rpc backend
# result_backend =  'redis://' # 'rpc://' # 'db+sqlite:///results.db'
## If set to True, result messages will be persistent. This means the messages won’t be lost after a broker restart.
result_persistent = False

task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'Asia/Shanghai'
enable_utc = True