#Pickle - following IDs, follower IDs, last_message_id, api key data? or api keys in environment variables
import twitter
try:
	import cPickle as pickle
except:
	import pickle
import os

FOLLOWER_TYPE = "followers"
FOLLOWING_TYPE = "following"

client = twitter.Api(consumer_key=os.environ['TEST_TWITTER_CON_KEY'], consumer_secret=os.environ['TEST_TWITTER_CON_SECRET'],access_token_key=os.environ['TEST_TWITTER_ACCESS_KEY'],access_token_secret=os.environ['TEST_TWITTER_ACCESS_SECRET'])

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

#messages all should be in order, this is just a backup check on the first page
#off messages in cases twitter craziness
def get_last_message_id():
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

twitter_data = {'follower_ids':get_ids("followers"),
		'following_ids':get_ids("following"),
		'last_message_id':get_last_message_id()}

with open('twitter_data.pkl', 'wb') as output:
	pickle.dump(twitter_data, output)

#with open('twitter_data.pkl', 'rb') as data:
#	print pickle.load(data)
