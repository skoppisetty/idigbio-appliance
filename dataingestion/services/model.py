#!/usr/bin/env python
#
# Copyright (c) 2013 Suresh Koppisetty <suresh.koppisetty@gmail.com>, University of
# Florida
#
# Extra layer of abstraction to Database model - Currently using sqlalchemy Manager
#
# This software may be used and distributed according to the terms of the
# MIT license: http://www.opensource.org/licenses/mit-license.php


import logging
from dataingestion.services.dbmodel import sql_model

logger = logging.getLogger("iDigBioSvc.Model")

model = sql_model

def setup(db_file):
	model.setup(db_file)

def close():
	model.close()

def commit():
	model.commit()

# api needed for REST API
def get_progress(task_id):
	if task_id is None:
		logger.error("No ongoing upload task.")
		return "No ongoing upload task."
	else :
		return model.get_batch_progress_brief(task_id)

def get_result(task_id):
	if task_id is None:
		logger.error("No ongoing upload task.")
		return "No ongoing upload task."
	else :
		return model.get_batch_result_brief(task_id)

def get_history(table_id):
	"""
	If batch_id is not given, return all batches.
	Otherwise, return the details of the batch with batch_id.
	"""
	if table_id is None or table_id == "":
		return model.get_all_batches()
	else:
		return model.get_batch_details_brief(table_id)


def add_batch(CSVfilePath, iDigbioProvidedByGUID,
	 RightsLicense, RightsLicenseStatementUrl, RightsLicenseLogoUrl, task_id):
	return model.add_batch(CSVfilePath, iDigbioProvidedByGUID,
		 RightsLicense, RightsLicenseStatementUrl, RightsLicenseLogoUrl, task_id)

def add_image(batch, row, headerline):
	record = model.add_image(batch, row, headerline)
	return record

def get_batch_details_fieldnames():
	return model.get_batch_details_fieldnames()

def get_batch_details_brief(batch_id):
	return model.get_batch_details_brief(batch_id)

def get_batch_details(batch_id):
	return model.get_batch_details(batch_id)

def get_unuploaded_information():
	return model.get_unuploaded_information()

def set_all_csv_uploaded():
	return model.set_all_csv_uploaded()

def get_all_success_details():
	return model.get_all_success_details()

def get_all_batches():
	return model.get_all_batches()

def get_last_batch_info():
	return model.get_last_batch_info()

def load_last_batch():
	return model.load_last_batch()

def get_csv_path(batch_id):
	return model.get_csv_path(batch_id)

# Todo: Change model to use update by api (identifier, key, newval)
def update_image(image_record_id, key, val):
	return model.update_image(image_record_id, key, val)

def get_image(image_record_id):
	record =  model.get_image(image_record_id)
	return record

def update_status(batch_id, error):
	return model.update_status(batch_id, error)

def update_batch(task_id, key, val):
	return model.update_batch(task_id, key, val)


