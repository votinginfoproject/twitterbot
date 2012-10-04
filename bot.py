import twitter
import os
import bitly_api
import requests
import json
import time
import pickle

QUERY_LIMIT = 5
FOLLOWER_TYPE = "followers"
FOLLOWING_TYPE = "following"
ELECTION_ID = 4000
GOOGLE_KEY = os.environ['GOOGLE_KEY']
GOOGLE_URL = "https://www.googleapis.com/civicinfo/us_v1/voterinfo/{0}/lookup?key={1}".format(ELECTION_ID, GOOGLE_KEY)
REQUEST_HEADER = {'content-type': 'application/json'}
POLLING_LOCATION_FIELDS = ["locationName","line1","line2","line3","city","state","zip"]
ERROR_REPLIES = {'noStreetSegmentFound':'Address not found, please check with your local election official for more information',
			'addressUnparseable':'Unable to read address, please enter only your address information'}

client = twitter.Api(consumer_key=os.environ['TEST_TWITTER_CON_KEY'], consumer_secret=os.environ['TEST_TWITTER_CON_SECRET'],access_token_key=os.environ['TEST_TWITTER_ACCESS_KEY'],access_token_secret=os.environ['TEST_TWITTER_ACCESS_SECRET'])
bit = bitly_api.Connection(os.environ['BITLY_USER'], os.environ['BITLY_KEY'])

def get_ids(id_type, cursor=-1):
	ids = set()
	while cursor != 0:
		try:
			if id_type == FOLLOWER_TYPE:
				data = client.GetFollowerIDs(cursor=cursor)
			elif id_type == FOLLOWING_TYPE:
				data = client.GetFriendIDs(cursor=cursor)
			else:
				break
			cursor = data["next_cursor"]
			ids = ids.union(set(data["ids"]))
		except:
			pass
	return ids

def get_new_ids(old_ids, id_type, cursor=-1):
	
	ids = get_ids(id_type, cursor)
	new_ids = ids.difference(old_ids)
	
	for user_id in new_ids:
		try:
			if id_type == FOLLOWER_TYPE: #we would be able to do this all in one statement, pop to pass in the id, but twitter over capacity errors mean we need to run CreateFriendship and pop separately
				client.CreateFriendship(user=user_id) 
			elif id_type == FOLLOWING_TYPE:
				client.PostDirectMessage(user=user_id, text="Message back with your address to receive polling location information")
			else:
				break
		except:
			pass
	return ids

def get_new_messages(last_message_id):
	messages = []
	try:
		messages = client.GetDirectMessages(since_id=last_message_id)
	except:
		pass
	return messages

def check_reply(reply):
	if len(reply) > 140 and reply.find("http") >= 0:
		start_of_url = reply.find("http") #could be https
		url = reply[start_of_url:].split(" ")[0]
		shortened_url = bit.shorten(url)
		reply = reply[:start_of_url] + shortened_url["url"] + reply[start_of_url+len(url):]
	if len(reply) > 140: #also will check post url shortening, just in case the response is still too long
		reply = reply[:reply[:140].rfind(" ")]
	if reply.rfind(",") > (len(reply) - 4): #if the response ends with a comma or comma is super close to the end, remove it
		reply = reply[:reply.rfind(",")]			
	return reply

def google_api_request(address):
	return json.loads(requests.post(GOOGLE_URL, data=json.dumps({'address':address}), headers=REQUEST_HEADER).text)

def send_response(sender_sn, reply):
	success = False
	reply = check_reply("@"+sender_sn+" "+reply)
	
	print "about to send: " + reply
	while not success:
		try:
			client.PostUpdate(status=reply)
			print "sent successfully"
			success = True
		except twitter.TwitterError as err:
			if str(err).find("You already said that") >= 0:
				reply = reply.split(" ")[0] + " Again:" + reply[reply.find(" "):]
				success = send_response(sender_sn, reply)
			elif str(err).find("Over Capacity") < 0:
				return success
		else:
			return success
	return success

def bad_request_reply(status):
	return ERROR_REPLIES[status]

def success_request_reply(polling_locations):
	reply = ""
	if len(polling_locations) > 1:
		reply += "Multiple polling locations, first listed:"
	location = polling_locations[0]
	if len(location["pollingHours"]) > 5 and location["pollingHours"].find("00:00") < 0:
		reply += str(location["pollingHours"]) + " at"
	reply += ' '.join(' '.join([location[f] for f in POLLING_LOCATION_FIELDS])).split()
	return reply	

with open('twitter_data.pkl', 'rb') as data:
	twitter_data = pickle.load(data)

#def main():
follower_ids = twitter_data['follower_ids']
following_ids = twitter_data['following_ids']
last_message_id = twitter_data['last_message_id']
messengers = {}

while 1:

	start = time.time()	

	follower_ids = get_new_ids(follower_ids, FOLLOWER_TYPE)
	following_ids = get_new_ids(following_ids, FOLLOWING_TYPE)

	messages = get_new_messages(last_message_id)

	for m in messages:
		sender_sn = m.sender_screen_name
		message_id = m.id
	
		if sender_sn in messengers and messengers[sender_sn]["query_count"] >= QUERY_LIMIT:
			if messengers[sender_sn]["query_count"] == QUERY_LIMIT:
				send_response(sender_sn, REPLIES["limit_error"])
				messengers[sender_sn]["query_count"] += 1
		else:
			if sender_sn in messengers:
				messengers[sender_sn]["query_count"] += 1
			else:
				messengers[sender_sn] = {}
				messengers[sender_sn]["query_count"] = 1
			response = google_api_request(m.text)
			if response['status'] == 'success' and len(response["pollingLocations"]) > 0:
				send_response(sender_sn, success_reply(response["pollingLocations"]))
			else:
				send_response(sender_sn, bad_request_reply(response["status"]))

		if message_id > last_message_id:
				last_message_id = message_id

	end = time.time()
	process_time = end - start
	pause = 20 - process_time
	if pause > 0:
		time.sleep(pause)

#if __name__ == "__main__":
#	try:
#		pid = fork()
#		if pid > 0:
#			exit(0)
#	except OSError, e:
#		exit(1)
	
#	chdir(os.getcwd())
#	setsid()
#	umask(0)

#	try:
#		pid = fork()
#		if pid > 0:
#			print "Daemon PID " + str(pid)
#			exit(0)
#	except OSError, e:
#		exit(1)

#	main()
