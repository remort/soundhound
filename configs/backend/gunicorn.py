workers = 1
bind = "0.0.0.0:8000"
loglevel = "debug"
reload = True
worker_class = 'aiohttp.worker.GunicornWebWorker'
#worker-class = aiohttp.worker.GunicornUVLoopWebWorker
