import requests
r = requests.get(
    "https://gordyjcn:Mys7JMiva5BHtzP4ezfGtamC4D73Jvja@donkey.rmq.cloudamqp.com/api/queues/gordyjcn/celery"
)
r.json()
