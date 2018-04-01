from common.const import *
import numpy as np
from collections import deque
import copy
import time
import json
import sys
import pickle
import common.analysisArgParser as argParser
import matplotlib.pyplot as plt

from Dependency.ObjectPreference import ObjectPreference
from Dependency.HourlyActionRate import HourlyActionRate
from Dependency.TypeDistribution import TypeDistribution
from common.simulationTime import SimulationTime


class IndependentAnalysisLib(object):
    _instance = None

    @staticmethod
    def getInstance():
        """ Static access method. """
        if IndependentAnalysisLib._instance is None:
            IndependentAnalysisLib()
        return IndependentAnalysisLib._instance

    def __init__(self , fileName = None):
        if IndependentAnalysisLib._instance is not None:
            raise Exception("IndependentAnalysisLib class is a singleton!")
        else:
            IndependentAnalysisLib._instance = self

        if fileName:
            self.fileName = DATAPATH + fileName
        else:
            self.fileName = DATAPATH + argParser.sargs.dataset

        self.userIds = {}
        self.objectIds = {}
        self.coreEventTypes = {"CreateEvent": 0, "DeleteEvent": 1, "ForkEvent": 2, "IssuesEvent": 3,
                               "PullRequestEvent": 4, "PushEvent": 5, "WatchEvent": 6}

        # Event count for the users
        self.userObjectCount = {}
        self.userHourlyCount = {}
        self.userTypeCount = {}

        # Statistics for the users
        self.userObjectPreference = {}
        self.userHourlyActionRate = {}
        self.userTypeDistribution = {}

        # Statistics for the new users.
        self.generalTotalActionCount = 0
        self.generalTypeDistribution = np.array([0.0 for i in range(7)])
        self.generalHourlyActionRate = np.array([0.0 for i in range(24)])

        # Statistics for inactive user cluster.
        self.inactiveUserIds = []
        self.inactiveUserCount = 0
        self.inactiveTotalActionCount = 0
        self.inactiveTypeDistribution = np.array([0.0 for i in range(7)])
        self.inactiveHourlyActionRate = np.array([0.0 for i in range(24)])

        # Statistics fro regular users.
        self.regularUserIds = []
        self.regularUserCount = 0
        self.regularTotalActionCount = 0

        # Statistics for active users
        self.activeUserIds = []
        self.activeUserCount = 0
        self.activeTotalActionCount = 0

        # In the first pass, we will get the general distribution and user activity level.
        self.firstPass()

        # The second pass, calculate the hourlyActionRate and objectPreference
        self.secondPass()


    def firstPass(self):
        '''
        The first pass, we will only count the userIds, objIds, user activity levels, and general distribution.
        :return:
        '''
        print("First pass...")

        with open(self.fileName, "r") as file:
            for line in file:
                if not line:
                    break
                else:
                    line = line.strip('\n')
                    eventTime, hour, objectId, userId, eventType = self.eventSplit(line)

                    # Skip the events types that we do not care.
                    if eventType not in self.coreEventTypes:
                        continue

                    # Update the objectIds and the event number
                    if objectId not in self.objectIds:
                        self.objectIds[objectId] = 1.0
                    else:
                        self.objectIds[objectId] += 1

                    # Update the userId and the action number
                    if userId not in self.userIds:
                        self.userIds[userId] = 1.0
                    else:  #Not a new user.
                        self.userIds[userId] += 1

                    #Update the general hourlyActionRate and typeDistribution
                    self.updateGeneralDistributions(hour, eventType)
                    self.generalTotalActionCount += 1

        for userId in self.userIds:
            if self.isActiveUser(userId):
                self.activeUserCount += 1
                self.activeUserIds.append(userId)
                self.activeTotalActionCount += self.userIds[userId]
            elif self.isInactiveUser(userId):
                self.inactiveUserCount += 1
                self.inactiveUserIds.append(userId)
                self.inactiveTotalActionCount += self.userIds[userId]
            else:
                self.regularUserCount += 1
                self.regularUserIds.append(userId)
                self.regularTotalActionCount += self.userIds[userId]

        # Extract the general hourlyActionRate and typeDistribution
        self.summarizeGeneralDistribtions()

    def secondPass(self):
        '''
        In this pass, we will compute the hourly action rate and object preference.

        Note: We will not compute hourly action rate for inactive users.
        :return:
        '''
        print("Second pass...")

        with open(self.fileName, "r") as file:
            for line in file:
                if not line:
                    break
                else:
                    line = line.strip('\n')
                    eventTime, hour, objectId, userId, eventType = self.eventSplit(line)

                    # Skip the events types that we do not care.
                    if eventType not in self.coreEventTypes:
                        continue

                    #Update the user hourly action rate for regular/active users, and inactive cluster.
                    if self.isInactiveUser(userId):
                        self.updateInactiveDistributions(hour, eventType)
                    else:
                        if userId not in self.userHourlyCount:
                            self.updateUserHourlyActionRate(userId, hour, "new")
                        else:
                            self.updateUserHourlyActionRate(userId, hour, "old")

                        if userId not in self.userTypeCount:
                            self.updateUserTypeDistribution(userId, eventType, "new")
                        else:
                            self.updateUserTypeDistribution(userId, eventType, "old")

                    #Upadate the object preference for all users
                    if userId not in self.userObjectCount:
                        self.updateUserObjectPreference(userId, objectId, "new")
                    else:
                        self.updateUserObjectPreference(userId, objectId, "old")

        #Update the userHourActionRate, userObjectPreference, and userTypeDistribution
        self.summarizeInactiveDistributions()
        self.summarizeUserDistributions()

    def eventSplit(self, line):
        '''
        Given a line of input, extract the attributes.
        :param line: A line of input with format #Event format: (eventTime, objectId, userId)
        :return:
        '''
        event = line.split(" ")
        eventTime = event[0]
        hour = SimulationTime.getHourFromIso(eventTime)
        objectId = event[1]
        userId = event[2]
        eventType = event[3]
        return eventTime, hour, objectId, userId, eventType

    def updateGeneralDistributions(self, hour, eventType):
        '''
        Update the general HourlyActionRate and ObjectPreference
        :param objId:
        :return:
        '''
        self.generalHourlyActionRate[hour] += 1

        typeIndex = self.coreEventTypes[eventType]
        self.generalTypeDistribution[typeIndex] += 1

    def updateInactiveDistributions(self, hour, eventType):
        '''
        Update the HourlyActionRate and ObjectPreference for inactive user cluster.
        :param hour:
        :param eventType:
        :return:
        '''
        self.inactiveHourlyActionRate[hour] += 1

        typeIndex = self.coreEventTypes[eventType]
        self.inactiveTypeDistribution[typeIndex] += 1

    def updateUserHourlyActionRate(self, userId, hour, userType):
        '''
        Upate the hourly action distribution of each user.
        :param userId:
        :param hour:
        :param userType:
        :return:
        '''
        if userType == "new":
            self.userHourlyCount[userId] = np.array([0.0 for i in range(24)])

        self.userHourlyCount[userId][hour] += 1

    def updateUserTypeDistribution(self, userId, eventType, userType):
        '''
        Update the event type distribution of each user.
        :param userId:
        :param eventType:
        :param userType:
        :return:
        '''
        if userType == "new":
            self.userTypeCount[userId] = np.array([0.0 for i in range(7)])

        typeIndex = self.coreEventTypes[eventType]
        self.userTypeCount[userId][typeIndex] += 1

    def updateUserObjectPreference(self, userId, objectId, userType):
        '''
        In the first pass, update the user object preference.
        :param userId:
        :param objectId:
        :param userType:
        :return:
        '''
        if userType == "new":
            self.userObjectCount[userId] = {objectId: 1.0}
        else:
            if objectId not in self.userObjectCount[userId]:  # Did not touch this object before
                self.userObjectCount[userId][objectId] = 1.0
            else:
                self.userObjectCount[userId][objectId] += 1

    def summarizeGeneralDistribtions(self):
        '''
        Compute the general distributions based on the general statistics.
        :return:
        '''
        self.generalTypeDistribution /= self.generalTotalActionCount

        self.generalHourlyActionRate /= self.generalTotalActionCount

    def summarizeInactiveDistributions(self):
        '''
        Compute the distributions for inactive user cluster.
        :return:
        '''
        self.inactiveTypeDistribution /= self.inactiveTotalActionCount

        self.inactiveHourlyActionRate /= self.inactiveTotalActionCount

    def summarizeUserDistributions(self):
        '''
        Summarize the user hourlyActionRate and objectPreference
        :return:
        '''
        for userId in self.userHourlyCount:
            self.userHourlyActionRate[userId] = self.userHourlyCount[userId] / self.userIds[userId]

        for userId in self.userTypeCount:
            self.userTypeDistribution[userId] = self.userTypeCount[userId] / self.userIds[userId]

        for userId in self.userObjectCount:
            self.userObjectPreference[userId] = {}
            for objectId in self.userObjectCount[userId]:
                self.userObjectPreference[userId][objectId] = \
                    self.userObjectCount[userId][objectId] / self.userIds[userId]

    def isActiveUser(self, userId):
        '''
        :param userId:
        :return: Return if this user is an active user, cause we only the influence of active users.
        '''
        return self.userIds[userId] > ACTIVE_THRESHOLD * ANALYSIS_LENGTH

    def isInactiveUser(self, userId):
        '''
        Judge if the given user is an inactive user.
        :param userId:
        :return:
        '''
        return self.userIds[userId] < INACTIVE_THRESHOLD * ANALYSIS_LENGTH

    def getUserIds(self):
        return self.userIds

    def getObjectIds(self):
        return self.objectIds

    def getEventTypes(self):
        return self.coreEventTypes.keys()

    def getUserHourlyActionRate(self, userId):
        '''
        :return: one HourlyRate instance;

        Note: Users below ActivityLevel will use the general distribution.
        '''
        if userId in self.userHourlyActionRate:
            userHourlyActionRate = HourlyActionRate(userId, self.userIds[userId]/ANALYSIS_LENGTH,
                                                    self.userHourlyActionRate[userId])
        else:  #This is a new user, no record; or he has too few records.
            if userId in self.userIds:
                userHourlyActionRate = HourlyActionRate(userId, self.userIds[userId]/ANALYSIS_LENGTH,
                                                    self.generalHourlyActionRate)
            else:
                averageDailyActivityLevel = float(self.generalTotalActionCount) / \
                                            (len(self.userIds.keys()) * ANALYSIS_LENGTH)
                userHourlyActionRate = HourlyActionRate(userId, averageDailyActivityLevel,
                                                        self.generalHourlyActionRate)
        return userHourlyActionRate

    def getUserObjectPreference(self, userId):
        '''
        :return: an ObjectPreference instance

        Note: Different from hourlyRate, each user with record will have a object preference.
        '''
        objectPreference = ObjectPreference(
            userId, list(self.userObjectPreference[userId].keys()),
            list(self.userObjectPreference[userId].values()))

        return objectPreference

    def getUserTypeDistribution(self, userId):
        '''
        Get the type action distribution of the given user.
        :param userId:
        :return:
        '''
        if userId in self.userTypeDistribution:
            typeDistribution = TypeDistribution(userId, self.userTypeDistribution[userId])
        else:
            typeDistribution = TypeDistribution(userId, self.generalTypeDistribution)

        return typeDistribution

    def storeStatistics(self):
        self.checkStatFolder()
        self.storeUserID()
        self.storeObjID()
        self.storeUserActionRate()
        self.storeUserObjectPreference()
        self.storeUserTypeDistribution()

    def checkStatFolder(self):
        if not os.path.exists(STAT_PATH):
            os.makedirs(STAT_PATH)

    def storeUserID(self):
        pickle.dump(self.userIds, open(USER_ID_FILE,'w'))

    def storeObjID(self):
        pickle.dump(self.objectIds, open(OBJ_ID_FILE,'w'))

    def storeUserActionRate(self):
        '''
        Store a general hourly rate here.
        :return:
        '''
        allActionRate = dict()
        for userId in self.userHourlyActionRate:
            if self.isActiveUser(userId):
                actionRate = self.getUserHourlyActionRate(userId)
                allActionRate[userId] = actionRate

        newUserActionRate = self.getUserHourlyActionRate(-1)
        allActionRate[-1] = newUserActionRate

        pickle.dump(allActionRate, open(USER_ACTION_RATE_FILE,'w'))

    def storeUserObjectPreference(self):
        '''
        No object preference for new user here. It is meaningless.
        :return:
        '''
        allObjectPreference = dict()
        for userId in self.userTypeDistribution:
            objectPreference = self.getUserObjectPreference(userId)
            allObjectPreference[userId] = objectPreference

        pickle.dump(allObjectPreference, open(USER_OBJECT_PREFERENCE_FILE,'w'))

    def storeUserTypeDistribution(self):
        '''
        Store a general type distribution here.
        :return:
        '''
        allTypeDistribution = dict()
        for userId in self.userTypeDistribution:
            if self.isActiveUser(userId):
                typeDistritbuion = self.getUserTypeDistribution(userId)
                allTypeDistribution[userId] = typeDistritbuion

        newUserTypeDistribution = self.getUserTypeDistribution(-1)
        allTypeDistribution[-1] = newUserTypeDistribution

        pickle.dump(allTypeDistribution, open(USER_TYPE_DISTRIBUTION_FILE, 'w'))

    def getMostActiveUser(self):
        '''
        Get the id of most active user.
        :return:
        '''
        return max(self.userIds, key=self.userIds.get)

    def plotGeneralHourlyDistribution(self):
        '''
        Function for plot the general general hourly activity distribution.
        :return:
        '''
        x = np.arange(0, 24)
        y = self.generalHourlyActionRate
        fig = plt.bar(x, y)
        plt.xlabel("Hour")
        # plt.xticks(x, x, rotation=-90)
        plt.ylabel("Proportion")
        plt.title("General hourly action ditribution")
        plt.show()

    def plotGeneralTypeDistribution(self):
        '''
        Function for plot the general type distribution.
        :return:
        '''
        x = self.coreEventTypes.keys()
        y = self.generalTypeDistribution
        fig = plt.bar(x, y)
        plt.tight_layout()
        plt.xlabel("Event Type")
        plt.xticks(x, x, rotation=-90)
        plt.ylabel("Proportion")
        plt.title("General action type distribution")
        plt.show()

    def plotUserHourlyDistribution(self, userId):
        '''
        Plot the hourly activity distribution for given user.
        :return:
        '''
        x = np.arange(0, 24)
        y = self.userHourlyActionRate[userId]
        plt.bar(x, y)
        plt.xlabel("Hour")
        # plt.xticks(x, x, rotation=-90)
        plt.ylabel("Proportion")
        plt.title("Hourly action distribution of user: %s"%userId)
        plt.show()

    def plotUserTypeDistribution(self, userId):
        '''
        Plot the type activity distribution for given user.
        :param userId:
        :return:
        '''
        x = self.coreEventTypes.keys()
        y = self.userTypeDistribution[userId]
        plt.bar(x, y)
        plt.tight_layout()
        plt.xlabel("Event Type")
        plt.xticks(x, x, rotation=-90)
        plt.ylabel("Count")
        plt.title("Action type distribution for user: %s"%userId)
        plt.show()


if __name__ == '__main__':
    start = time.time()
    fileName = sys.argv[1]
    independentAnalysisLib = IndependentAnalysisLib(fileName)
    end = time.time()
    print("Analyze time: %f s"%(end-start))

    print("Number of active users: %d"%len(independentAnalysisLib.userHourlyActionRate.keys()))
    print("Average daily activity level: %f"%(independentAnalysisLib.generalTotalActionCount /
                                              (len(independentAnalysisLib.userIds) *
                                              ANALYSIS_LENGTH)))
    print("Average number of repos: %d"%(independentAnalysisLib.generalTotalActionCount /
                                         len(independentAnalysisLib.userIds)))

    # # mostActiveuser = independentAnalysisLib.getMostActiveUser()
    # print("Number of users: %d"%len(independentAnalysisLib.userIds.keys()))
    # print("Number of objects: %d"%len(independentAnalysisLib.objectIds.keys()))
    print(independentAnalysisLib.generalTypeDistribution)
    print(independentAnalysisLib.inactiveTypeDistribution)
    print(independentAnalysisLib.generalHourlyActionRate)
    print(independentAnalysisLib.inactiveHourlyActionRate)
    mostActiveuser = "mGzHxRUb6V36nyFJgEXPeQ"
    # mostActiveuser = "YyAXRlZYVhUlbHCublQjzg"
    # independentAnalysisLib.plotUserHourlyDistribution(mostActiveuser)
    # independentAnalysisLib.plotUserTypeDistribution(mostActiveuser)
