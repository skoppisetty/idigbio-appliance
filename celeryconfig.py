import sys
sys.path.append('.')

# currently using redis - extra dependency 
# Have to look into replacing this with sqlalchemy
BROKER_URL = 'redis://localhost:6379/'
CELERY_RESULT_BACKEND = "redis://localhost:6379/0"

CELERY_ACCEPT_CONTENT = ['pickle']
CELERY_TASK_SERIALIZER = 'pickle'
CELERY_RESULT_SERIALIZER = 'pickle'

CELERY_IMPORTS = ("dataingestion.services.manager.celery_handler", )
