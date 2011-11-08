#!/usr/bin/python

#could use an threaded Timer from the Timer class to run this on an interval
#every 60 seconds, or could have it make the calls every 60 seconds if the timer has not yet expired, this is more manual and ugly code-wise, but prevents possible overlapping calls to users
import datetime, time, twitter, urllib, urllib2, json
from os import fork, chdir, setsid, umask
import os
from sys import exit

#TODO:Hardcore in admin websites?

BASEURL = "https://pollinglocation.googleapis.com/?"
ELECT_ID_DICT = {"ohio":2006, "oh":2006, "connecticut":2007, "ct":2007, "mississippi":2009, "ms":2009, "north carolina":2002, "nc":2002, "pennsylvania":2008, "pa":2008, "virginia":2010, "va":2010}
POLLING_HOURS = {"OH":"6:30am - 7:30pm", "VA":"6am - 7pm", "CT":"6am - 8pm", "MS":"7am - 7pm", "NC":"6:30am - 7:30pm", "PA":"7am - 8pm"}
APIVERSION = '1.1'
INTERVAL = 60 

def get_state(message):
	state = ""
	if message.find(":") >= 0:
		state = message.split(":")[0]
	elif message.find(",") >= 0:
		state = message.split(",")[0]
	elif message.find(" ") >= 0:
		state = message.split(" ")[0]
	if state.find(" ") >= 0:
		state = ''.join([c for c in state.split(" ")[0].lower() if c.isalpha()]) + " " + ''.join([c for c in state.split(" ")[1].lower() if c.isalpha()])
	else:
		state = ''.join([c for c in state.lower() if c.isalpha()])
	if state in ELECT_ID_DICT:
		return state
	return None

def get_address(message):
	address = None 
	if message.find(":") >= 0:
		address = message[message.find(":")+1:]
	elif message.find(",") >= 0:
		address = message[message.find(",")+1:]
	elif message.find(" ") >= 0:
		address = message[message.find(" ")+1:]
	return address

def bad_request_reply(response):
	reply = "Could not find polling location for this address"
	if "stateInfo" in response:
		if "where_to_vote" in response["stateInfo"] and len(response["stateInfo"]["where_to_vote"]) > 0:
			reply += ". Check " + response["stateInfo"]["where_to_vote"] + " for polling location information"
		elif "election_website" in response["stateInfo"] and len(response["stateInfo"]["election_website"]) > 0:
			reply += ". Check " + response["stateInfo"]["election_website"] + " for polling location information"
	if len(reply) > 140:
		reply = "Missing info, check " + reply[56:]
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

def write_logs(log_data, w):
	w.write("Log Totals: \tMessages: " + str(log_data["messages"]) + " \tMentions: " + str(log_data["mentions"]) + " \tRepeat Lookups: " + str(log_data["repeat_lookups"]) + "\n")
	w.write("State Info: \tOhio: " + str(log_data["ohio"] + log_data["oh"]) + " \tMississippi: " + str(log_data["mississippi"] + log_data["ms"]) + " \tPennsylvania: " + str(log_data["pennsylvania"] + log_data["pa"]) + " \tNorth Carolina: " + str(log_data["north carolina"] + log_data["nc"]) + " \tConnecticut: " + str(log_data["connecticut"] + log_data["ct"]) + " \tVirginia: " + str(log_data["virginia"] + log_data["va"]) + "\n")
	w.write("Errors: \tFollowing Errors: " + str(log_data["following_errors"]) + " \tLookup Errors: " + str(log_data["lookup_errors"]) + " \tState Request Errors: " + str(log_data["state_request_errors"]) + " \tMax Request Errors: " +str(log_data["max_request_errors"]) +  " \tHard Errors: " + str(log_data["hard_errors"]) + "\n") 

def main():
	bot_start_time = time.time()

	w = open("twitterbot.log", "a")
	w.write("**************************************************\n")
	w.write("Bot run started at: " + str(datetime.datetime.now().isoformat()) + "\n")
	w.write("Using election date: " + str(ELECT_ID_DICT) + "\n")
	w.write("**************************************************\n")
	w.close()

	#all this oauth shit now required by twitter, python-twitter uses this fine
	client = twitter.Api(consumer_key='<consumer_key>', consumer_secret='<consumer_secret>',access_token_key='<access_token_key>',access_token_secret='<access_token_secret>')

	#should be able to safely store a following_list in memory, each follower = 64 bytes, but if shit gets crazy than this might not be an option
	following_list = {}
	try:
		following = []
		following = client.GetFriends()
	except:
		pass
	#creating the initial follower list, any successful DM will add the user to this list
	for f in following:
		following_list[f.id] = {}
		following_list[f.id]["user"] = f
		following_list[f.id]["query_count"] = 0

	public_mentions = []
	to_follow = {} #deal with latency issues
	last_mention_id = 0
	last_message_id = 0
	data = {"q":"", "electionid":"", "api_version":APIVERSION}
	total_logs = {"ohio":0, "oh":0, "connecticut":0, "ct":0, "mississippi":0, "ms":0, "north carolina":0, "nc":0, "pennsylvania":0, "pa":0, "virginia":0, "va":0, "messages":0, "mentions":0, "following_errors": 0, "repeat_lookups":0, "hard_errors":0, "lookup_errors":0, "state_request_errors":0, "max_request_errors":0}
	first_pass = True
	cycle_count = 0

	while 1:
		cycle_count += 1
		start  = time.time()
		cycle_logs = dict([(k, 0) for (k, v) in total_logs.iteritems()])
		try:
			following = client.GetFriendIDs()
		except:
			pass
		if len(following) > 0 and "ids" in following:
			for following_id in following["ids"]:
				if following_id in to_follow:
					try:
						client.PostDirectMessage(user=following_id,text="Message back with an address in the format 'State Name:Address' (ex. 'Virginia:11700 Lariat Ln, Oakton, VA 22124') for polling location data")
						following_list[following_id] = {}
						following_list[following_id]["user"] = to_follow.pop(following_id)
						following_list[following_id]["query_count"] = 0
					except:
						try:
							if following_id not in public_mentions:
								client.PostUpdate(status="@"+to_follow[following_id].user.screen_name+ " Please make sure you are following us and @reply again so we can Direct Message your polling location")
								public_mentions.append(following_id)
							cycle_logs["following_errors"] += 1
						except:
							pass
		try:
			mentions = []
			mentions = client.GetReplies(since_id=last_mention_id)
		except:
			pass	
		cycle_logs["mentions"] = len(mentions)
		for m in mentions:
			userid = m.user.id 
			if not(userid in following_list) and m.created_at_in_seconds > bot_start_time:
				try:
					client.CreateFriendship(user=userid)
					to_follow[userid] = m.user	
				except:
					pass
			if m.id > last_mention_id:
				last_mention_id = m.id
		try:
			followers = []
			followers = client.GetFollowers()
		except:
			pass	
		for f in followers:
			userid = f.id
			if not userid in following_list:
				try:
					client.CreateFriendship(user=userid)	
					to_follow[userid] = f
				except:
					pass
		if first_pass:
			first_pass = False
			try:
				temp_messages = []
				temp_messages = client.GetDirectMessages()
			except:
				pass
			messages = []
			for tm in temp_messages:
				if tm.created_at_in_seconds > bot_start_time:
					messages.append(tm)
				if tm.id > last_message_id:
					last_message_id = tm.id
			cycle_logs["messages"] = len(messages)
		elif not first_pass and last_message_id > 0:
			try:
				messages = []
				messages = client.GetDirectMessages(since_id=last_message_id)
			except:
				pass
			cycle_logs["messages"] = len(messages)
		
		for m in messages:
			sender_id = m.sender_id
			if (sender_id in following_list):
				following_list[sender_id]["query_count"] += 1
				if following_list[sender_id]["query_count"] > 1:
					cycle_logs["repeat_lookups"] += 1
				if following_list[sender_id]["query_count"] == 7:
					reply = "You have reached the polling lookup limit for today"
					cycle_logs["max_request_errors"] += 1
				elif following_list[sender_id]["query_count"] < 7:
					state = get_state(m.text)
					address = get_address(m.text)
					if state is None or address is None:
						reply = "No data found Supported states: OH, CT, MS, NC, PA, VA. If your state is listed, check spelling, use State:Address format and message again"
						cycle_logs["state_request_errors"] += 1 
					else:
						data["q"] = address
						cycle_logs[state] += 1
						data["electionid"] = ELECT_ID_DICT[state.lower()]
						edata = urllib.urlencode(data)
						response = json.load(urllib2.urlopen(BASEURL+edata))
						if response["status"] != "SUCCESS" or not "locations" in response or len(response["locations"]) == 0:
							if "stateInfo" in response and (state != response["stateInfo"]["state_long"].lower() and state != response["stateInfo"]["state_abbr"].lower()):
								reply = "Error looking up polling location"
								cycle_logs["hard_errors"] += 1
							else:
								reply = bad_request_reply(response)
								cycle_logs["lookup_errors"] += 1
						else:
							reply = success_request_reply(response)			
			try:
				if len(reply) > 140:
					reply = reply[:reply[:140].rfind(" ")]
				if reply.rfind(",") > (len(reply) - 4):
					reply = reply[:reply.rfind(",")]
				if m.id > last_message_id:
					last_message_id = m.id #put this before the message sending, just in case there's an error, want to continue through messages
				status = client.PostDirectMessage(user=sender_id,text=reply)
			except twitter.TwitterError as err:
				if str(err).find("You already said that") >= 0:
					reply = "Again: " + reply
					if reply.find("Missing info") >= 0:
						reply = "Again: missing polling location info, check you state administrator's website for more info"
					if len(reply) > 140:
						reply = reply[:reply[:140].rfind(" ")]
					if reply.rfind(",") > (len(reply) - 4):
						reply = reply[:reply.rfind(",")]
					try:
						status = client.PostDirectMessage(user=sender_id,text=reply)
					except:
						pass
				else:
					try:
						if sender_id not in public_mentions:
							client.PostUpdate(status="@"+m.sender_screen_name+ " message error, make sure you are following us and @reply again for your polling location",in_reply_to_status_id=m.id)
							public_mentions.append(sender_id)
						cycle_logs["following_errors"] += 1
					except:
						pass
			except:
				pass
		for key in total_logs:
			total_logs[key] += cycle_logs[key]
		w = open("twitterbot.log", "a")
		w.write("Log data at: " + str(datetime.datetime.now().isoformat()) + "\n")
		w.write("Cycle Log Data: \n")
		write_logs(cycle_logs, w)
		w.write("Total Log Data: \n")
		write_logs(total_logs, w)
		end = time.time()
		process_time = end - start
		pause = INTERVAL - process_time
		cycle_time = "Cycle: " + str(cycle_count) + " \tProcess Time: " + str(process_time) + " \tPause Time: " + str(pause) + "\n"
		w.write(cycle_time)
		w.close()
		if pause > 0:
			time.sleep(pause)

if __name__ == "__main__":
	try:
		pid = fork()
		if pid > 0:
			exit(0)
	except OSError, e:
		exit(1)
	
	chdir(os.getcwd())
	setsid()
	umask(0)

	try:
		pid = fork()
		if pid > 0:
			print "Daemon PID " + str(pid)
			exit(0)
	except OSError, e:
		exit(1)

	main()
