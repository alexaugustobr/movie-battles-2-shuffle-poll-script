#!/usr/bin/python2.7

"""
License: MIT

Description:
	Poll like script for mb2, for shuffle the team, to vote type !sf or !shuffle

Requirements:
	* Python 2.7
	* Updated Movie battles 2 and Jedi academy
	* Server with log enabled, example config with cvars:
		* seta g_log "server.log"
		* seta g_logClientInfo "1"
		* seta g_logSync "1"
		* seta g_logExplicit "3"

Todo:
    * Ao mudar de mapa, resetar o shuffle
    * Nao contar votos de spec
	* Tempo limite de votacao
	* Encapsular app
	* Mensagens customizadas para o minimo de jogadores para o shuffle
	* Thread assincrona para mensagens de status do shuffle poll

Special thanks to:
	* Lucas arts
	* Jedi academy developer team
	* Movie Battles 2 developer team
	* OpenJediAcademy team
	* Movie Battles 2 Brasil team
	* Tigao

Author: https://github.com/alexcologia33

Last version: https://github.com/alexcologia33/mb2-jedi-academy-scripts/tree/master/shuffle
"""

import datetime
import json
import os
import re
import socket
import time
import unicodedata

CONFIG_FILE_NAME = 'shuffle-config.json'

class ConfigLoader:
	def loadConfigAsDict(self):
		with open(CONFIG_FILE_NAME) as json_data_file:
			data = json.load(json_data_file, encoding='iso-8859-1')
			return data

def normalize(string):
	return unicodedata.normalize('NFKD', string).encode('ascii', 'ignore')


data = ConfigLoader().loadConfigAsDict()

SERVER_LOG_PATH = os.path.expanduser(normalize(data['SERVER_LOG_PATH']))
SERVER_RCON_PWD = normalize(data['SERVER_RCON_PWD'])
SERVER_IP = normalize(data['SERVER_IP'])
SERVER_PORT = normalize(data['SERVER_PORT'])

REGEX_SAY_COMMAND = r'(.[0-9]*:.[0-9]*) (.*[0-9]:) (say:) (.*:) ("!(shuffle|sf)")'

REGEX_PLAYER_Disconnected = r'(ClientDisconnect:(.[0-9]*))'

MSG_ONLINE = 'Shuffle poll is on!'

MSG_VOTATION_PASS = 'Shuffle passed!'

MSG_VOTATION_FAIL = 'Shuffle failed!'

MSG_VOTATION_INITIALIZED = 'Shuffle poll initialized!'

VOTATION_MAX_TIME_TO_FAIL = 5

MSG_TOTAL_PLAYERS_WANTS = '{} players wants to shuffle, more {} needed!'

MSG_PLAYER_WANT = '{} ^7wants to Shuffle the team!'

MSG_PLAYER_REMOVED_FROM_VOTES = 'Player {} ^7was disconnected his \'shuffle\' vote was been removed.'

DEFAULT_MESSAGE_DECODER = 'iso-8859-1'

LOOP_TIME = 5

IS_DEBUG_ENABLED = True

SHUFFLE_ENABLED = 'Shuffle poll is enabled on the server! Say ^3!sf ^7or ^3!shuffle ^7for vote!'

MIN_PLAYERS_TO_VOTE = 2

MIN_PERCENT_PLAYERS_TO_WIN = 0.6

getOnlyDigitsAsInt = lambda x: int(filter(str.isdigit, x) or None)

MSG_RESTART_SCRIPT = 'Restarting the script.'

class Console:
	@staticmethod
	def info(message):
		finalMessage = '({}) INFO: {}'.format(datetime.datetime.now(), message)
		print(finalMessage)
	@staticmethod
	def debug(message):
		if IS_DEBUG_ENABLED:
			finalMessage = '({}) DEBUG: {}'.format(datetime.datetime.now(), message)
			print(finalMessage)

	@staticmethod
	def error(message):
		finalMessage = '({}) ERROR: {}'.format(datetime.datetime.now(), message)
		print(finalMessage)

class LogFile:
	def __init__(self, serverLogPath):
		self.serverLogPath = serverLogPath
		self._lastChangeTime = self.getChangeTime()
		self.lastLineNumber = self.readAndGetLastLineNumber()

	def read(self):
		return open(self.serverLogPath, 'r+')

	def readAsArray(self):
		file = self.read()
		lines = []

		for line in file:
			lines.append(line)

		return lines

	def readAndGetLastLineNumber(self):
		return sum(1 for line in open(self.serverLogPath, 'r+'))
	
	def getChangeTime(self):
		return os.stat(self.serverLogPath).st_mtime

	def isChanged(self):
		stamp = self.getChangeTime()
		if stamp != self._lastChangeTime:
			self._lastChangeTime = stamp
			self.lastLineNumber = self.readAndGetLastLineNumber()
			return True
		else:
			return False
		
class VoteExtractor:

	def __init__(self, regex):
		self.regex = regex

	def extract(self, stringToExtract):
		result = re.search(self.regex, stringToExtract)

		if (not result):
			return None

		messageId = result.group(1).strip()
		playerId = result.group(2).strip()
		playerName = result.group(4).strip().replace(':', '')#fix for regex
		optionMessage = result.group(5).strip()
		
		return Vote(messageId, playerId, playerName, optionMessage)

class PlayerDisconnectedExtractor:

	def __init__(self, regex):
		self.regex = regex

	def extract(self, stringToExtract):
		result = re.search(self.regex, stringToExtract)

		if (not result):
			return None

		playerId = result.group(2).strip()

		return int(getOnlyDigitsAsInt(playerId))

class Poll:

	def __init__(self):
		pass

	voteDict = {}
	totalVotes = 0
	totalPlayers = 0
	
	def addVote(self, vote):
		playerId = int(getOnlyDigitsAsInt(vote.playerId))
		self.voteDict[playerId] = vote
		poll.calculate()

	def playerHasVoted(self, playerId):
		if playerId is None:
			return False

		voted = playerId in self.voteDict.keys()
		return voted

	def removeVote(self, playerId):
		if playerId in self.voteDict.keys():
			del self.voteDict[playerId]
			poll.calculate()

	def calculate(self):
		self.totalVotes = len(self.voteDict.keys())

	def reset(self):
		self.voteDict = {}
		self.totalVotes = 0
		self.totalPlayers = 0

	def isPassed(self):
		return self.totalVotes >= self.totalVotesNeedToWin()

	def totalVotesNeedToWin(self):
		if self.totalPlayers <= MIN_PLAYERS_TO_VOTE:
			return MIN_PLAYERS_TO_VOTE
		
		return int(round(MIN_PERCENT_PLAYERS_TO_WIN * self.totalPlayers))

	def __str__(self):
		strx = """
		totalVotes = {}
		totalPlayers = {}
		totalVotesNeedToWin = {}
		isPassed = {}
		""".format(self.totalVotes, self.totalPlayers, self.totalVotesNeedToWin(), self.isPassed())
		return strx
		

class Vote:

	def __init__(self, messageId, playerId, playerName, optionMessage):
		self.messageId = messageId
		self.playerId = playerId
		self.playerName = playerName
		self.optionMessage = optionMessage 

	def __str__(self):

		strx = """
		messageId = {}
		playerId = {}
		playerName = {}
		optionMessage  = {}
		""".format(self.messageId, self.playerId, self.playerName, self.optionMessage)

		return strx

class Server:

	REGEX_PLAYER_COUNT = r'(\\clients\\(.[0-9]*)\\)'

	def __init__(self, host, port, rconPassword):
		self.rconPassword = rconPassword
		self.host = host
		self.port = port

	def sendData(self, data):
		data = ("\xff\xff\xff\xff%s\n" % data)
		#Console.debug("%r"%data)
		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		sock.sendto(data, (self.host, getOnlyDigitsAsInt(self.port)))
		receivedData = self.recvWithTimeout(sock)
		decodeMessage = receivedData.decode(DEFAULT_MESSAGE_DECODER).strip()
		return decodeMessage

	def sendRconCmdWithParameter(self, cmd, parameter):
		data = ("rcon %s %s %s" % (self.rconPassword, cmd, parameter))
		self.sendData(data)

	def sendRconCmd(self, cmd):
		data = ("rcon %s %s" % (self.rconPassword, cmd))
		self.sendData(data)

	def sendCmd(self, cmd):
		return self.sendData(cmd)

	def sendMessage(self, msg):
		Console.info(msg)
		self.sendRconCmdWithParameter("svsay", msg)

	def sendShuffle(self):
		self.sendRconCmd("shuffle")

	def requestStatus(self):
		return self.sendCmd("getstatus")

	def requestInfo(self):
		return self.sendCmd("getinfo")

	def requestPlayerCount(self):
		info = self.requestInfo()

		#igore all escape characters, because the string come just like this \clients\
		raw_txt = "%r"%info

		result = re.search(self.REGEX_PLAYER_COUNT, raw_txt)

		if not result:
			return 0

		textNumber = result.group(2)	

		return getOnlyDigitsAsInt(textNumber)

	def recvWithTimeout(self, the_socket,timeout=2):
		#make socket non blocking
		the_socket.setblocking(0)
		#total data partwise in an array
		total_data=[];
		data='';
		#beginning time
		begin=time.time()
		while True:
			#if you got some data, then break after timeout
			if total_data and time.time()-begin > timeout:
				break
			#if you got no data at all, wait a little longer, twice the timeout
			elif time.time()-begin > timeout*2:
				break
			#recv something
			try:
				data = the_socket.recv(8192)
				if data:
					total_data.append(data)
					#change the beginning time for measurement
					begin=time.time()
				else:
					#sleep for sometime to indicate a gap
					time.sleep(0.1)
			except:
				pass
		#join all parts to make final string
		return ''.join(total_data)


if __name__ == "__main__":
	while True:
		try:
			logFile = LogFile(SERVER_LOG_PATH)
			lastReadedLineNumber = logFile.lastLineNumber
			voteExtractor = VoteExtractor(REGEX_SAY_COMMAND)
			playerDisconnectedExtractor = PlayerDisconnectedExtractor(REGEX_PLAYER_Disconnected)
			server = Server(SERVER_IP, SERVER_PORT, SERVER_RCON_PWD)

			server.sendMessage(SHUFFLE_ENABLED)

			poll = Poll()

			while True:
				time.sleep(LOOP_TIME)
				#Console.debug(poll)
				#Will only read the unreaded lines if the file has been changed
				if logFile.isChanged():
					poll.totalPlayers = server.requestPlayerCount()
					#Console.debug('File has changed, reading the new lines only!')
					text = logFile.readAsArray()

					for i in range(lastReadedLineNumber, logFile.lastLineNumber):
						textLine = text[i]
						Console.debug("line {}: {}".format(i, textLine))
						vote = voteExtractor.extract(textLine)

						if vote and not poll.playerHasVoted(getOnlyDigitsAsInt(vote.playerId)):
							poll.addVote(vote)
							server.sendMessage(MSG_PLAYER_WANT.format(vote.playerName))

							if poll.totalVotes > 0:
								server.sendMessage(
									MSG_TOTAL_PLAYERS_WANTS.format(poll.totalVotes, poll.totalVotesNeedToWin()-poll.totalVotes))

						disconnectedPlayerId = playerDisconnectedExtractor.extract(textLine)

						if poll.playerHasVoted(disconnectedPlayerId):
							poll.removeVote(disconnectedPlayerId)
							server.sendMessage(MSG_PLAYER_REMOVED_FROM_VOTES.format(disconnectedPlayerId))

							if poll.totalVotes > 0:
								server.sendMessage(
									MSG_TOTAL_PLAYERS_WANTS.format(poll.totalVotes, poll.totalPlayers))

					lastReadedLineNumber = logFile.lastLineNumber
					# double check, this may be not necessary
					poll.calculate()
					Console.info(poll)

					if poll.isPassed():
						server.sendMessage(MSG_VOTATION_PASS)
						poll.reset()
						server.sendShuffle()

		except Exception as e:
			Console.error(e)
			Console.info(MSG_RESTART_SCRIPT)
			time.sleep(LOOP_TIME*2)


			


