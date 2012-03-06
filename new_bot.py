import twitter
import bitly_api
import time
import urllib
import urllib2
import json
import datetime

QUERY_LIMIT = 5
FOLLOWER_TYPE = "followers"
FOLLOWING_TYPE = "following"
STARTING_CURSOR = -1
REPLIES = {"limit_error":"",
		"state_error":"Supported states include VA, MS, and OH. If you entered one of the states, please check spelling and send address in the format 'State:Address' and try again",}
API_VERSION = "1.1"
BASEURL = "https://pollinglocation.googleapis.com/?"
NAME_TO_ABBREV = {'VERMONT': 'VT', 'GEORGIA': 'GA', 'IOWA': 'IA', 'GUAM': 'GU', 'KANSAS': 'KS', 'FLORIDA': 'FL', 'VIRGINIA': 'VA', 'NORTH CAROLINA': 'NC', 'ALASKA': 'AK', 'NEW YORK': 'NY', 'CALIFORNIA': 'CA', 'ALABAMA': 'AL', 'TEXAS': 'TX', 'FEDERATED STATES OF MICRONESIA': 'FM', 'IDAHO': 'ID', 'ARMED FORCES AMERICAS': 'AA', 'DELAWARE': 'DE', 'HAWAII': 'HI', 'ILLINOIS': 'IL', 'CONNECTICUT': 'CT', 'DISTRICT OF COLUMBIA': 'DC', 'MISSOURI': 'MO', 'NEW MEXICO': 'NM', 'PUERTO RICO': 'PR', 'OHIO': 'OH', 'MARYLAND': 'MD', 'ARKANSAS': 'AR', 'MASSACHUSETTS': 'MA', 'SOUTH DAKOTA': 'SD', 'TENNESSEE': 'TN', 'PALAU': 'PW', 'COLORADO': 'CO', 'ARMED FORCES MIDDLE EAST': 'AE', 'NEW JERSEY': 'NJ', 'UTAH': 'UT', 'MICHIGAN': 'MI', 'WYOMING': 'WY', 'WASHINGTON': 'WA', 'MINNESOTA': 'MN', 'OREGON': 'OR', 'AMERICAN SAMOA': 'AS', 'VIRGIN ISLANDS': 'VI', 'MARSHALL ISLANDS': 'MH', 'ARMED FORCES PACIFIC': 'AP', 'SOUTH CAROLINA': 'SC', 'INDIANA': 'IN', 'NEVADA': 'NV', 'LOUISIANA': 'LA', 'NORTHERN MARIANA ISLANDS': 'MP', 'ARIZONA': 'AZ', 'WISCONSIN': 'WI', 'NORTH DAKOTA': 'ND', 'MONTANA': 'MT', 'PENNSYLVANIA': 'PA', 'OKLAHOMA': 'OK', 'KENTUCKY': 'KY', 'RHODE ISLAND': 'RI', 'MISSISSIPPI': 'MS', 'NEBRASKA': 'NE', 'NEW HAMPSHIRE': 'NH', 'WEST VIRGINIA': 'WV', 'MAINE': 'ME'}
ELECTION_IDS = {"OH":2110, "MS":2111, "VA":2109}

client = twitter.Api(consumer_key='', consumer_secret='',access_token_key='',access_token_secret='')
bit = bitly_api.Connection('', '')

last_message_id = 0 #the logs should output the last message id and then the bot should have a parameter for last_message_id on start up that we can use in case the bot shuts down so that we can start it up again right where it left off
#TODO: More debugging an logging

def get_ids(id_type, cursor=-1):
	ids = []
	while cursor != 0:
		try:
			if id_type == FOLLOWER_TYPE:
				data = client.GetFollowerIDs(cursor=cursor)
			elif id_type == FOLLOWING_TYPE:
				data = client.GetFriendIDs(cursor=cursor)
			else:
				break
			cursor = data["next_cursor"]
			ids.extend(data["ids"])
		except:
			pass
	return ids	

def get_new_ids(old_ids, id_type, cursor=-1):
	
	ids = get_ids(id_type, cursor)
	new_ids = [userid for userid in ids if not userid in old_ids]
	
	while len(new_ids) > 0:
		try:
			if id_type == FOLLOWER_TYPE: #we would be able to do this all in one statement, pop to pass in the id, but twitter over capacity errors mean we need to run CreateFriendship and pop separately
				client.CreateFriendship(user=new_ids[len(new_ids)-1]) 
			elif id_type == FOLLOWING_TYPE:
				client.PostDirectMessage(user=new_ids[len(new_ids)-1], text="Message back with an address in the format 'State Name:Address'")
			else:
				break
			new_ids.pop()
		except:
			pass
	return ids 

def get_old_messages():
	success = False
	last_id = 0
	messages = []
	while not success:
		try:
			messages = client.GetDirectMessages()
			success = True
		except twitter.TwitterError as err: 
			if str(err).find("Capacity Error") < 0: # if error is not a capacity error, then break out of the while loop
				break
		
	for m in messages:
		if m.id > last_id:
			last_id = m.id
	return last_id

def get_new_messages():
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
		
def send_response(sender_id, reply):
	success = False
	reply = check_reply(reply)
	
	print "about to send: " + reply
	while not success:
		try:
			status = client.PostDirectMessage(user=sender_id,text=reply)
			print "sent successfully"
			success = True
		except twitter.TwitterError as err:
			if str(err).find("You already said that") >= 0:
				reply = "Again: " + reply
				success = send_response(sender_id, reply)
			elif str(err).find("Over Capacity") < 0:
				return success
		else:
			return success
	return success

def get_state_address(message):
	state = ""
	address = ""
	split_index = message.find(":")
	if split_index < 0:
		split_index = message.find(",")
		if split_index < 0:
			split_index = message.find(" ")
	state = message[:split_index]
	state = ''.join([c for c in state.upper() if c.isalpha() or c == " "]) 
	if len(state) > 2 and state in NAME_TO_ABBREV:
		state = NAME_TO_ABBREV[state]
	address = message[split_index + 1:]
	return state, address		

def access_google_api(address, election_id):
	request = {"api_version":API_VERSION, "q":address, "electionid":election_id}
	edata = urllib.urlencode(request)
	return json.load(urllib2.urlopen(BASEURL+edata))

def valid_response(response):
	return (response["status"] == "SUCCESS" and "locations" in response and len(response["locations"]) >= 0)

def bad_request_reply(response):
	if "stateInfo" in response and state == response["stateInfo"]["state_abbr"].upper():
		reply = REPLIES["lookup_error"]
		if "stateInfo" in response:
			if "where_to_vote" in response["stateInfo"] and len(response["stateInfo"]["where_to_vote"]) > 0:
				reply += ". Check " + response["stateInfo"]["where_to_vote"] + " for polling location information"
			elif "election_website" in response["stateInfo"] and len(response["stateInfo"]["election_website"]) > 0:
				reply += ". Check " + response["stateInfo"]["election_website"] + " for polling location information"
	else:
		reply = REPLIES["hard_error"]
	return reply

def success_request_reply(response):
	reply = ""
	location = response["locations"][0]
	if "polling_hours" in location and len(location["polling_hours"]) > 0 and location["polling_hours"].find("00:00") < 0:
		reply += str(location["polling_hours"]) + " at"
	elif "address" in location and "state" in location["address"]:
		reply += str(POLLING_HOURS[location["address"]["state"].upper()]) + " at"
	if "address" in location and len(location["address"]) > 0:
		address = location["address"]
		if "location_name" in address and len(address["location_name"]) > 0:
			reply += " " + address["location_name"]
		if "line1" in address and len(address["line1"]) > 0:
			reply += " " + address["line1"]
		if "line2" in address and len(address["line2"]) > 0:
			reply += " " + address["line2"]
		if "city" in address and len(address["city"]) > 0:
			reply += " " + address["city"]
		if "state" in address and len(address["state"]) > 0:
			reply += ", " + address["state"]
		if "zip" in address and len(address["zip"]) > 0:
			reply += " " + address["zip"][:5]
	if "directions" in location and len(location["directions"]) > 0:
		reply += ", " + location["directions"]
	return reply

old_follower_ids = get_ids(FOLLOWER_TYPE, STARTING_CURSOR)
old_following_ids = get_ids(FOLLOWING_TYPE, STARTING_CURSOR)
messages = []
first_pass = True
cycle_count = 0
messengers = {}
public_mentions = []


while 1:
	
	start = time.time()
	cycle_count += 1

	follower_ids = get_new_ids(old_follower_ids, FOLLOWER_TYPE, STARTING_CURSOR)
	following_ids = get_new_ids(old_following_ids, FOLLOWING_TYPE, STARTING_CURSOR)

	if first_pass:
		last_message_id = get_old_messages()
		first_pass = False
	else:
		messages = get_new_messages()

	for m in messages:
		sender_id = m.sender_id
		message_id = m.id
		if sender_id in following_ids:
			if sender_id in messengers and messengers[sender_id]["query_count"] >= QUERY_LIMIT:
				if messengers[sender_id]["query_count"] == QUERY_LIMIT:
					send_response(sender_id, REPLIES["limit_error"])
					messengers[sender_id]["query_count"] += 1
			else:
				if sender_id in messengers:
					messengers[sender_id]["query_count"] += 1
				else:
					messengers[sender_id] = {}
					messengers[sender_id]["query_count"] = 1
				state, address = get_state_address(m.text)
				if state not in ELECTION_IDS or len(address) == 0:
					send_response(sender_id, REPLIES["state_error"])
				else:
					response = access_google_api(address, ELECTION_IDS[state])
					print response
					if valid_response(response):
						send_response(sender_id, success_reply(response))
					else:
						send_response(sender_id, bad_request_reply(response))
		elif sender_id not in public_mentions:	
			try:
				client.PostUpdate(status="@"+m.sender_screen_name+REPLIES["message_error"],in_reply_to_status_id=m.id)
				public_mentions.append(sender_id)
			except:
				pass
		if message_id > last_message_id:
				last_message_id = message_id
	
	end = time.time()
	process_time = end - start
	pause = 20 - process_time
	cycle_time = "Cycle: " + str(cycle_count) + " \tProcess Time: " + str(process_time) + " \tPause Time: " + str(pause) + "\n"
	print cycle_time
	if pause > 0:
		time.sleep(pause)

print "Followers: " + str(len(follower_ids))
print "Following: " + str(len(following_ids))
