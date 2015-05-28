#!/usr/bin/python

"""
This file defines routines that can call the recording service to start/stop message logging
"""

PKG = "rosbag_record_service"
import roslib; roslib.load_manifest(PKG)
from record_service.srv import *
import rospy

def make_request(action, topic_group):
    rospy.wait_for_service('record_service')
    try:
        record_request = rospy.ServiceProxy('record_service', RecordSrv)
        action = RecordSrvRequest.START if action=="start" else RecordSrvRequest.STOP
        response = record_request(action, topic_group)
        print response.return_code
    except rospy.ServiceException as e:
        print "Service call failed: %s" % e


if __name__ == "__main__":
    # Initialize the client node so that we can get the required parameters
    rospy.init_node('record_service_client')
    try:
        action = rospy.get_param('~action')
        topic_group = rospy.get_param('~topic_group')
        make_request(action, topic_group)
    except KeyError as e:
        print "Missing argument. Usage: _action:=[start/stop] _topic_group:=topic"
        print e
