#!/usr/bin/env python

"""Get SMS message records from a Twilio account for a specified time period.

usage: getsms.py [-h] [-s START] [-e END] [--tz TZ] [-a ACCOUNT] [-p PW]
                 [--subs] [--fields FIELDS] [--version]
                 [--log {debug,info,warning}]
                 sms_file

    positional arguments:
    sms_file                    output CSV file

    optional arguments:
    -h, --help                  show this help message and exit
    -s START, --start START     start at this date/time (YYYY-MM-DD [[HH:MM:SS]±HHMM];
                                default: start of last month)
    -e END, --end END           end before this date/time (YYYY-MM-DD [[HH:MM:SS]±HHMM];
                                default: start of this month)
    --tz TZ                     timezone as ±HHMM offset from UTC (default: timezone
                                of local machine)
    -a ACCOUNT, --account ACCOUNT
                                account SID (default: TWILIO_ACCOUNT_SID env var)
    -p PW, --pw PW              auth token (default: TWILIO_AUTH_TOKEN env var)
    --subs                      include subaccounts
    --fields FIELDS             comma-separated list of desired fields (default: all)
    --version                   show program's version number and exit
    --log {debug,info,warning}  set logging level

Add a filename to the command line prefixed by '@' if you wish to place
parameters in a file, one parameter per line.
"""


import argparse
import csv
import logging
import os
import sys
from datetime import datetime

from twilio.base.exceptions import TwilioException
from twilio.rest import Client


__version__ = "1.0.0"

SMS_FIELDS = [
    "sid",
    "date_created",
    "date_updated",
    "date_sent",
    "account_sid",
    "to",
    "from",
    "messaging_service_sid",
    "body",
    "status",
    "num_segments",
    "num_media",
    "direction",
    "api_version",
    "price",
    "price_unit",
    "error_code",
    "error_message",
    "uri",
    "subresource_uris",
]

logger = logging.getLogger(__name__)


def configure_logging(level=logging.INFO):
    logger.setLevel(level)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d: %(message)s', datefmt='%H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def parse_field_list(value):
    fields = [field.strip() for field in value.lower().split(',') if field.strip()]
    if not fields:
        raise argparse.ArgumentTypeError("argument is empty")

    for field in fields:
        if field not in SMS_FIELDS:
            raise argparse.ArgumentTypeError(f"{field} is not a recognized SMS field")

    return fields


def parse_tzinfo(value):
    try:
        return datetime.strptime(value, '%z').tzinfo
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Timezone offset should be a signed value in the form ±HHMM")


def get_args():

    now = datetime.now()
    last_month = 12 if now.month == 1 else now.month - 1
    year_of_last_month = now.year - 1 if last_month == 12 else now.year
    first_of_this_month = datetime(day=1, month=now.month, year=now.year)
    first_of_last_month = datetime(day=1, month=last_month, year=year_of_last_month)
    local_timezone = now.astimezone().tzinfo

    parser = argparse.ArgumentParser(
        description="Get SMS message records from a Twilio account for a specified time period.",
        epilog=("Add a filename to the command line prefixed by '@' if you wish to place "
                "parameters in a file, one parameter per line."),
        fromfile_prefix_chars='@')
    parser.add_argument('sms_file', help="output CSV file")
    parser.add_argument(
        '-s', '--start', type=datetime.fromisoformat, default=first_of_last_month,
        help="start at this date/time (YYYY-MM-DD [[HH:MM:SS]±HH:MM]; default: start of last month)")
    parser.add_argument(
        '-e', '--end', type=datetime.fromisoformat, default=first_of_this_month,
        help="end before this date/time (YYYY-MM-DD [[HH:MM:SS]±HH:MM]; default: start of this month)")
    parser.add_argument(
        '--tz', default=local_timezone, type=parse_tzinfo,
        help="timezone as ±HHMM offset from UTC (default: timezone of local machine)")
    parser.add_argument(
        '-a', '--account', default=os.environ.get('TWILIO_ACCOUNT_SID'),
        help="account SID (default: TWILIO_ACCOUNT_SID env var)")
    parser.add_argument(
        '-p', '--pw', default=os.environ.get('TWILIO_AUTH_TOKEN'),
        help="auth token (default: TWILIO_AUTH_TOKEN env var)")
    parser.add_argument('--subs', action='store_true', help="include subaccounts")
    parser.add_argument(
        '--fields', default=SMS_FIELDS, type=parse_field_list,
        help="comma-separated list of desired fields (default: all)")
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument(
        '--log', choices=['debug', 'info', 'warning'], default='info',
        help="set logging level")
    args = parser.parse_args()

    if args.start.tzinfo is None:
        args.start = args.start.replace(tzinfo=args.tz)
    if args.end.tzinfo is None:
        args.end = args.end.replace(tzinfo=args.tz)

    if args.start >= args.end:
        parser.error("Start date is after end date")
    if not args.account:
        parser.error("No account SID found")
    if not args.pw:
        parser.error("No auth token found")

    return args


def messages(args):
    client = Client(args.account, args.pw)

    try:
        if args.subs:
            accounts = client.api.accounts.list()
        else:
            accounts = [client.api.accounts(args.account).fetch()]

        for account in accounts:
            logger.info("Getting messages for account %s (%s)", account.sid, account.friendly_name)
            client = Client(args.account, args.pw, account.sid)
            yield from client.messages.list(
                date_sent_after=args.start,
                date_sent_before=args.end)

    except TwilioException as ex:
        sys.exit(f"Unable to get SMS messages: check credentials. Full message:\n{ex}")


def main(args):
    configure_logging(level=getattr(logging, args.log.upper()))
    logger.info("Getting SMS messages for the period %s to %s", args.start, args.end)
    logger.debug("Writing SMS records...")

    with open(args.sms_file, 'w', encoding='utf-8', newline='') as sms_file:
        writer = csv.writer(sms_file)
        writer.writerow(args.fields)

        sdk_fields = ['_from' if field == 'from' else field for field in args.fields]
        for message in messages(args):
            writer.writerow([getattr(message, field, None) for field in sdk_fields])

    logger.debug("Finished writing SMS records")


if __name__ == "__main__":
    main(get_args())