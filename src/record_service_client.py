#!/usr/bin/python

"""
This file defines routines that can call the recording service to start/stop message logging
"""

PKG = "record_service"
import argparse
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
    arg_parser = argparse.ArgumentParser(description='Calls the record_service node to start/stop recording')
    arg_parser.add_argument('--action', dest='action', required=True, type=str, help='[start/stop] recording')
    arg_parser.add_argument('--config_file', dest='config_file', required=True, type=str,
                            help='Absolute path to yaml config file')
    arg_parser.add_argument('--topic_group', dest='topic_group', required=True, type=str,
                            help='Topic group that is in the config file')
    args = arg_parser.parse_args()
    make_request(args.action, args.config_file, args.topic_group)
