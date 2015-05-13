#!/usr/bin/env python
#
# Copyright (c) 2013 Suresh Koppisetty <suresh.koppisetty@gmail.com>, University of
# Florida
#
# Extra layer of abstraction to ingestion manager - Currently using Celery Manager
#
# This software may be used and distributed according to the terms of the
# MIT license: http://www.opensource.org/licenses/mit-license.php

import logging, os, sys

# import celery manager - replace this with new manager
from dataingestion.services.manager.celery_manager import Celery_manager  
from dataingestion.services import user_config
from dataingestion.services import model
from dataingestion.services.user_config import (get_user_config,
                                                set_user_config, rm_user_config)

logger = logging.getLogger("iDigBioSvc.ingestion_manager")

class IngestServiceException(Exception):
  def __init__(self, msg, reason=''):
    Exception.__init__(self, msg)
    self.reason = reason

class InputCSVException(Exception): 
  def __init__(self, msg, reason=''):
    Exception.__init__(self, msg)
    self.reason = reason

# manager has to handle setup and start_upload api
manager = Celery_manager()

def setup(worker_thread_count):
	# Todo: Needs to handle this thread count
	# It can be done in main.py while running celery
	manager.setup(worker_thread_count)

def start_upload(values, task_id):
	if values == None:
		logger.debug("Resume last batch.")
		oldbatch = model.load_last_batch()
		if oldbatch.finish_time and oldbatch.FailCount == 0:
			logger.error("Last batch already finished, why resume?")
			error = 'Last batch already finished, why resume?'
			return error
		# Assign local variables with values in DB.
		values = {}
		values[user_config.CSV_PATH] = oldbatch.CSVfilePath
		values['RightsLicense'] = oldbatch.RightsLicense
	else:
		logger.debug("starting new task")
	# Initial checks before the task is added to the queue.
	path = values[user_config.CSV_PATH]
	if not os.path.exists(path):
		error = 'CSV file \"' + path + '\" does not exist.'
		logger.error(error)
		return error
		# raise ValueError(error)
	elif os.path.isdir(path):
		error = 'The CSV path is a directory.'
		logger.error(error)
		return error
		# raise ValueError(error)
	logger.debug("All checks done")
	try:
		error = manager.start_upload(values, task_id)
		return error
	except:
		logger.debug("Unexpected error:" + str(sys.exc_info()[0]))
		return str(sys.exc_info()[0])
