#!/usr/bin/python

"""
This file defines routines that can call the recording service to start/stop message logging
"""

PKG = "record_service"
import roslib; roslib.load_manifest(PKG)
from record_service.srv import *
import rospy

def make_request(action, config_file, topic_group):
    rospy.wait_for_service('record_service')
    try:
        record_request = rospy.ServiceProxy('record_service', RecordSrv)
        response = record_request(action, config_file, topic_group)
        print response.return_code, response.output
    except rospy.ServiceException as e:
        print "Service call failed: %s" % e


if __name__ == "__main__":
    # Initialize the client node so that we can get the required parameters
    rospy.init_node('record_service_client')
    try:
        action = rospy.get_param('~action')
        config_file = rospy.get_param('~config_file')
        topic_group = rospy.get_param('~topic_group')
        make_request(action, config_file, topic_group)
    except KeyError as e:
        print "Missing argument. Usage: _action:=[start/stop] _config_file:=/path/to/file _topic_group:=topic"
        print e
