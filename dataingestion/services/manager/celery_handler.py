from os.path import join, exists 
import os, site, csv, json
current_dir = os.path.abspath(os.getcwd())
site.addsitedir(join(current_dir, "lib"))
from celery import Celery
from datetime import datetime
import threading, json, appdirs, logging, tempfile, hashlib
from etc import constants
from dataingestion.services import user_config, model, api_client
from dataingestion.services.api_client import (ClientException, Connection,
                                               ServerException)
from dataingestion.services.user_config import (get_user_config,
                                                set_user_config, rm_user_config)

app = Celery('celery_handler',backend='redis://localhost:6379/', broker='redis://localhost:6379/')
# app.config_from_object('celeryconfig')

logger = logging.getLogger("iDigBioSvc.celery_handler")

# Needs to go in userconfig file
APP_NAME = 'iDigBio Data Ingestion Tool'
APP_AUTHOR = 'iDigBio'
USER_CONFIG_FILENAME = 'user.conf'
data_folder = appdirs.user_data_dir(APP_NAME, APP_AUTHOR)
user_config_path = join(data_folder, USER_CONFIG_FILENAME)
user_config.setup(user_config_path)
db_file = join(data_folder, APP_AUTHOR + ".ingest.db")

import redislite
red_con = redislite.Redis('/tmp/redis.db')

commit_lock = threading.Lock()


def init():
	model.setup(db_file)

def authenticate():
	api_client.init("http://beta-media.idigbio.org")
	api_client.authenticate(get_user_config('accountuuid'),
	                          get_user_config('apikey'))

init()

def _get_conn():
  """
  Get connection.
  """
  return Connection()

redis_lock = threading.Lock()


def get_stats(task_id, val):
	with red_con.lock(task_id):
		status  = json.loads(red_con.get(task_id))
		return status[val]

def check_finish(task_id):
	with red_con.lock(task_id):
		status  = json.loads(red_con.get(task_id))
		if status["FailCount"] + status["SuccessCount"] + status["SkipCount"] == status["recordCount"]:
			return True
		else:
			return False


def update_stats(task_id, update, val):
	with red_con.lock(task_id):
		status  = json.loads(red_con.get(task_id))
		logger.debug(json.dumps(status))
		if update == "SkipCount":
			# already updated to db
			status["SkipCount"] += 1
		elif update == "recordCount":
			# already updated to db
			status["recordCount"] += 1
		else:
			if val == None:
				status["SuccessCount"] += 1
				commit_lock.acquire()
				model.update_batch(task_id, "SuccessCount", status["SuccessCount"])
				commit_lock.release()
			else:
				status["FailCount"] += 1
				commit_lock.acquire()
				model.update_batch(task_id, "FailCount", status["FailCount"])
				commit_lock.release()
				status["Errors"].append(val)
		logger.debug(json.dumps(status))
		red_con.set(task_id, json.dumps(status))
		if check_finish(task_id):
			return True, json.dumps(status["Errors"])
		else:
			return False, None

@app.task
def _upload_task(task_id, values):
	authenticate()
	logger.debug("starting task " + str(task_id))
	# Get license details
	CSVfilePath = values[user_config.CSV_PATH]
	iDigbioProvidedByGUID = user_config.get_user_config(
	user_config.IDIGBIOPROVIDEDBYGUID)
	RightsLicense = values[user_config.RIGHTS_LICENSE]
	license_set = constants.IMAGE_LICENSES[RightsLicense]
	RightsLicenseStatementUrl = license_set[2]
	RightsLicenseLogoUrl = license_set[3]
	# add batch to db
	# adding task_id to batch details
	
	status = {}
	status["recordCount"] = 0
	status["SkipCount"] = 0
	status["SuccessCount"] =0
	status["FailCount"] =0
	status["Errors"] = []
	red_con.set(task_id, json.dumps(status))
	commit_lock.acquire()
	batch = model.add_batch(CSVfilePath, iDigbioProvidedByGUID,
	 RightsLicense, RightsLicenseStatementUrl, RightsLicenseLogoUrl, task_id)
	model.commit()
	batch_id = str(batch.id)
	conn = _get_conn()
	with open(CSVfilePath, 'rb') as csvfile:
		csv.register_dialect('mydialect', delimiter=',', quotechar='"',
                           skipinitialspace=True)
		reader = csv.reader(csvfile, 'mydialect')
		headerline = None
		recordCount = 0
		for row in reader: # For each line do the work.
			if not headerline:
				model.update_batch(task_id, "ErrorCode", "CSV File Format Error.")
				headerline = row
				model.update_batch(task_id, "ErrorCode", "")
				continue

			# Validity test for each line in CSV file  
			if len(row) != len(headerline):
				logger.debug("Input CSV File weird. At least one row has different"
					+ " number of columns")
				raise InputCSVException("Input CSV File weird. At least one row has"
					+ " different number of columns")

			for col in row: 
				if "\"" in col:
					logger.debug("One of CSV field contains \"(Double Quatation)")
					raise InputCSVException("One of CSV field contains Double Quatation Mark(\")") 

			# Get the image record
			image_record = model.add_image(batch, row, headerline)
			model.commit()
			update_stats(task_id , "recordCount", 1)
			if image_record is None:
				# Skip this one because it's already uploaded.
				# Increment skips count and return.
				# Todo : Need a way to identify these skips 
				print "skip"
				model.update_batch(task_id, "SkipCount", batch.SkipCount + 1)
				update_stats(task_id, "SkipCount", 1)
			else:
				print "upload", image_record
				logger.error(image_record.id)
				_upload_single_image.apply_async((image_record.id,batch_id,conn,task_id),link_error=_upload_images_error_handler.s())
      	recordCount = recordCount + 1
      	commit_lock.release()
      	commit_lock.acquire()
      # Save record count to db
   	model.update_batch(task_id, "RecordCount", get_stats(task_id , "recordCount"))
   	model.commit()
   	if check_finish(task_id):
   		model.update_status(batch_id, get_stats(task_id , "Errors"))
   		# post csv
   		_upload_csv(batch_id, _get_conn())
   	commit_lock.release()
 	# Done saving tasks
	logger.debug('Put all image records into db done.')

@app.task
def _upload_single_image(image_record_id, batch_id, conn, task_id):
	filename = ""
	mediaGUID = ""
	authenticate()
	commit_lock.acquire()
	logger.debug("uploading")
	logger.error(image_record_id)
	image_record = model.get_image(image_record_id)
	try:
		if not image_record:
			logger.error("image_record is None.")
			raise ClientException("image_record is None.")
		
		logger.info("Image job started: OriginalFileName: {0}"
        .format(image_record.OriginalFileName))

		if image_record.Error:
			logger.error("image record has error: {0}".format(image_record.Error))
			raise ClientException(image_record.Error)
		filename = image_record.OriginalFileName
		mediaGUID = image_record.MediaGUID
	finally:
		commit_lock.release()

	try:
		# Post image to API.
		# ma_str is the return from server
		img_str = conn.post_image(filename, mediaGUID)
		#    image_record.OriginalFileName, image_record.MediaGUID)
		result_obj = json.loads(img_str)
		url = result_obj["file_url"]
		# img_etag is not stored in the db.
		img_etag = result_obj["file_md5"]

		commit_lock.acquire()
		# try:
		# First, change the batch ID to this one. This field is overwriten.
		model.update_image(image_record_id, "BatchID" , batch_id)
		model.update_image(image_record_id, "MediaAPContent" , img_str)
		# Check the image integrity.
		if img_etag and image_record.MediaMD5 == img_etag:
			model.update_image(image_record_id, "UploadTime" , str(datetime.utcnow()))
			model.update_image(image_record_id, "MediaURL" , url)
		else:
			logger.error("Upload failed because local MD5 does not match the eTag"
				+ " or no eTag is returned.")
			raise ClientException("Upload failed because local MD5 does not match"
				+ " the eTag or no eTag is returned.")
		# commit model
		model.commit()
		# finally:
		commit_lock.release()

		if conn.attempts > 1:
			logger.debug('Done after %d attempts' % (conn.attempts))

		logger.debug("uploaded " + filename + str(batch_id) )
		Error = None
	except ClientException as ex:
		logger.error("ClientException: An image job failed. Reason: %s" %ex)
		Error = "ClientException"
		raise
	except IOError as err:
		logger.error("IOError: An image job failed.")
		Error = "IOError"
		if err.errno == ENOENT:
			logger.error("ENOENT")
		else:
			logger.error("Error IOError")
			raise
	except:
		logger.error("Fatal Server Error Detected")
		Error = "Fatal Server Error Detected"
	finally:
		# commit_lock.acquire()
		logger.debug("updating status " + str(batch_id))
		status, err =  update_stats(task_id, "Finish", Error)
		if status:
			commit_lock.acquire()
			# post csv
			_upload_csv(batch_id, _get_conn())
			model.update_status(batch_id, err)
			commit_lock.release()
		# model.update_status(batch_id, Error)
		# model.commit()
		# commit_lock.release()


@app.task(bind=True)
def _upload_task_error_handler(self, uuid):
	result = self.app.AsyncResult(uuid)
	print('Task {0} raised exception: {1!r}\n{2!r}'.format(
	    uuid, result.result, result.traceback))

@app.task(bind=True)
def _upload_images_error_handler(self, uuid):
	result = self.app.AsyncResult(uuid)
	print('Task {0} raised exception: {1!r}\n{2!r}'.format(
	    uuid, result.result, result.traceback))

#Todo
def _upload_csv(batch_id, conn):
  '''
  We upload all the unuploaded records together.
  '''
  try:
    logger.debug("CSV job started.")

    # Post csv file to API.
    # ma_str is the return from server
    name, f_md5 = _make_csvtempfile()
    csv_str = conn.post_csv(name)
    result_obj = json.loads(csv_str)

    # img_etag is not stored in the db.
    csv_etag = result_obj['file_md5']

    # Check the image integrity.
    if csv_etag != f_md5:
      logger.error("Upload failed because local MD5 does not match the eTag"
          + " or no eTag is returned.")
      raise ClientException("Upload failed because local MD5 does not match"
          + " the eTag or no eTag is returned.")
    logger.debug('Done after %d attempts' % (conn.attempts))
    # ongoing_upload_task.set_csv_uploaded()
    model.set_all_csv_uploaded()
  except ClientException as ex:
    logger.error("ClientException: A CSV job failed. Reason: %s" %ex)
    raise
  except IOError as err:
    logger.error("IOError: A CSV job failed.")
    raise

def _make_csvtempfile():
  logger.debug("Making temporary CSV file ...")
  fname = os.path.join(tempfile.gettempdir(), "temp.csv")
  md5 = ""
  with open(fname, "wb") as f:
    csvwriter = csv.writer(
        f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    header = model.get_batch_details_fieldnames()
    csvwriter.writerow(header)
    rows = model.get_unuploaded_information()
    for row in rows:
      csvwriter.writerow(row)
  with open(fname, "rb") as f:
    md5 = _md5_file(f)
  logger.debug("Making temporary CSV file done.")
  return fname, md5

def _md5_file(f, block_size=2*20):
  md5 = hashlib.md5()
  while True:
    data = f.read(block_size)
    if not data:
      break
    md5.update(data)
  return md5.hexdigest()
