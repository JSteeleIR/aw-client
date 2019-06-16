#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import timedelta, datetime, timezone
from pprint import pprint

import aw_client
from aw_core import Event


def _valid_date(s):
    # https://stackoverflow.com/questions/25470844/specify-format-for-input-arguments-argparse-python
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


# From http://code.activestate.com/recipes/577058/
def _query_yes_no(question, default='no'):
    """Ask a yes/no question via raw_input() and return their answer.

    'question' is a string that is presented to the user.
    'default' is the presumed answer if the user just hits <Enter>.
        It must be 'yes' (the default), 'no' or None (meaning
        an answer is required of the user).

    The 'answer' return value is True for 'yes' or False for 'no'.
    """
    valid = {'yes': True, 'y': True, 'ye': True, 'no': False, 'n': False}
    if default is None:
        prompt = ' [y/n] '
    elif default == 'yes':
        prompt = ' [Y/n] '
    elif default == 'no':
        prompt = ' [y/N] '
    else:
        raise ValueError('invalid default answer: "%s"' % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write('Please respond with "yes" or "no" '
                             '(or "y" or "n").\n')


class AWCLIHelper(object):
    """Defines helper methods used throughout aw-cli."""

    def __init__(self, host, port, testing=False, protocol='http'):
        self.client = aw_client.ActivityWatchClient(host=host,
                                                    port=port,
                                                    testing=testing,
                                                    protocol=protocol)

    def CreateHeartbeat(self, bucket, data, timestamp, pulsetime):
        """Create a heartbeat and send it to the server."""
        e = Event(duration=0, data=json.loads(data), timestamp=timestamp)
        print(e)
        self.client.heartbeat(bucket, e, pulsetime)

    def ListBuckets(self):
        """Query the server for buckets and print them out."""
        buckets = self.client.get_buckets()
        print("Buckets:")
        for bucket in buckets:
            print(" - {}".format(bucket))

    def CreateBucket(self, bucket, buckettype):
        """Create a bucket with the given name and type."""
        self.client.create_bucket(bucket, buckettype)
        self.ListBuckets()

    def DeleteBucket(self, bucket, force):
        """Delete the given bucket. Prompts for confirmation unless forced."""
        if force:
            self.client.delete_bucket(bucket)
        elif _query_yes_no("Really Delete bucket %s" % bucket, "no"):
            self.client.delete_bucket(bucket)

    def ListEvents(self, bucket, limit):
        events = self.client.get_events(bucket)
        print("events:")
        for e in events:
            print(" - {} ({}) {}".format(
                e.timestamp.replace(tzinfo=None, microsecond=0),
                str(e.duration).split(".")[0], e.data))

    def QueryEvents(self, query, start, end, cache, name, print_json):
        result = self.client.query(query, start, end, cache=cache, name=name)
        if print_json:
            print(json.dumps(result))
        else:
            for period in result:
                print("Showing 10 out of {} events:".format(len(period)))
                for event in period[:10]:
                    event.pop("id")
                    event.pop("timestamp")
                    print(" - Duration: {} \tData: {}".format(
                        str(timedelta(
                            seconds=event["duration"])).split(".")[0],
                        event["data"]))
                print("Total duration:\t",
                      timedelta(seconds=sum(e["duration"] for e in period)))


def main():
    now = datetime.now(timezone.utc)
    td1day = timedelta(days=1)
    td1yr = timedelta(days=365)

    # Top-Level Argument Parser:
    parser = argparse.ArgumentParser(
        prog='aw-cli',
        description='A CLI utility for interacting with ActivityWatch.')
    parser.set_defaults(which='none')
    parser.add_argument('--host',
                        default='localhost:5600',
                        help='Host to use, on the format HOSTNAME:PORT')
    parser.add_argument("--testing",
                        action="store_true",
                        help='run in testing mode')

    subparsers = parser.add_subparsers(help='sub-command help')

    # 1st-Level subcommand parsers:
    parser_heartbeat = subparsers.add_parser(
        'heartbeat', help='Send a heartbeat to the server')
    parser_buckets = subparsers.add_parser('buckets',
                                           help='List/Manage Buckets')
    parser_events = subparsers.add_parser('events', help='List/Manage Events')
    parser_query = subparsers.add_parser('query',
                                         help='Query events from bucket')

    # Heartbeat subcommand parser:
    parser_heartbeat.set_defaults(which='heartbeat')
    parser_heartbeat.add_argument('--pulsetime',
                                  default=60,
                                  help='Pulsetime to use')
    parser_heartbeat.add_argument('bucket',
                                  help='bucketname to send heartbeat to')
    parser_heartbeat.add_argument('data',
                                  default='{}',
                                  help='JSON data to send in heartbeat')

    # Buckets subcomand parser (List, Add, Delete):
    parser_buckets.set_defaults(which='buckets')
    buckets_subparser = parser_buckets.add_subparsers(
        title='buckets', help='List/Manage Buckets')
    buckets_list_parser = buckets_subparser.add_parser('list',
                                                       help='List Buckets')
    buckets_add_parser = buckets_subparser.add_parser('add',
                                                      help='Add a Bucket')
    buckets_delete_parser = buckets_subparser.add_parser(
        'delete', help='Delete a Bucket')

    # 2nd-Level 'buckets' subcommand parsers:
    buckets_list_parser.set_defaults(which='buckets.list')
    buckets_add_parser.set_defaults(which='buckets.add')
    buckets_add_parser.add_argument('bucket')
    buckets_add_parser.add_argument('type')
    buckets_delete_parser.set_defaults(which='buckets.delete')
    buckets_delete_parser.add_argument('bucket')
    buckets_delete_parser.add_argument('--force')

    # Events subcommand parser (List, add, modify, delete):
    parser_events.set_defaults(which='events')
    events_subparser = parser_events.add_subparsers(title='events',
                                                    help='List/Manage Events')

    # 2nd-Level 'events' subcommand parsers:
    events_list_parser = events_subparser.add_parser('list',
                                                     help='List Events')
    events_list_parser.set_defaults(which='events.list')
    events_list_parser.add_argument('bucket',
                                    help='The bucket to list events from.')
    events_list_parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='The number of events to retrieve from the bucket.')
    events_add_parser = events_subparser.add_parser('add', help='Add Events')
    events_add_parser.set_defaults(which='events.add')
    events_add_parser.add_argument('bucket',
                                   help='The bucket to add an event to.')
    events_add_parser.add_argument('data',
                                   default='{}',
                                   help='JSON data for the event.')
    events_add_parser.add_argument('--duration',
                                   type=int,
                                   help='Duration of the event in seconds.')
    events_add_parser.add_argument(
        '--squash_within',
        type=int,
        default=0,
        help=(
            'Lookback period in seconds for which to squash prior events.'
            'Overwrites events beginning within this range with the data '
            'provided for this event, and sets the start time for this event '
            'to the start time from the earliest event squashed. '
            'Defaults to "0" for no-squashing.'))
    #  TODO:  <09-06-19, jsteeleir> # Add Modify Events
    # events_mod_parser = events_subparser.add_parser('modify', help='Modify Events')
    events_delete_parser = events_subparser.add_parser('delete',
                                                       help='Delete Events')
    events_delete_parser.set_defaults(which='events.delete')
    events_delete_parser.add_argument(
        'bucket', help='The bucket to delete the event from.')
    events_delete_parser.add_argument(
        '--force', help='Delete the events without prompting')

    parser_query.set_defaults(which='query')
    parser_query.add_argument('path')
    parser_query.add_argument('--name')
    parser_query.add_argument('--cache', action='store_true')
    parser_query.add_argument('--json',
                              action='store_true',
                              help='Output resulting JSON')
    parser_query.add_argument('--start',
                              default=now - td1day,
                              type=_valid_date)
    parser_query.add_argument('--end',
                              default=now + 10 * td1yr,
                              type=_valid_date)

    args = parser.parse_args()
    # print("Args: {}".format(args))

    cli = AWCLIHelper(host=args.host.split(':')[0],
                      port=args.host.split(':')[1],
                      testing=args.testing)

    # TODO: Implement this as switch-case, instead of if/else.
    if args.which == "heartbeat":
        cli.CreateHeartbeat(args.bucket, args.data, now, args.pulsetime)
    elif args.which == "buckets.list":
        cli.ListBuckets()
    elif args.which == "buckets.add":
        cli.CreateBucket(args.bucket, args.type)
    elif args.which == "buckets.delete":
        cli.DeleteBucket(args.bucket, args.force)
    elif args.which == "events":
        parser_events.print_help()
    elif args.which == "events.list":
        cli.ListEvents(args.bucket, args.limit)
    elif args.which == "query":
        with open(args.path) as f:
            query = f.read()
            cli.QueryEvents(query, args.start, args.end, args.cache, args.name,
                            args.json)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
