"""Run native transcription libraries outside the desktop process."""
import faulthandler
import json
import sys
import traceback

# The private interpreter ignores machine/user environment variables.
# Keep the worker protocol UTF-8 even on a GBK-configured Windows desktop.
for stream in (sys.stdout, sys.stderr):
    if stream is not None:
        stream.reconfigure(encoding='utf-8', errors='replace')
faulthandler.enable()


def emit(kind, text):
    print(json.dumps({'kind': kind, 'text': text}, ensure_ascii=False), flush=True)


def main():
    import argparse
    from recorder import Session
    parser = argparse.ArgumentParser()
    parser.add_argument('session')
    parser.add_argument('--settings-json')
    args = parser.parse_args()
    try:
        session = Session(args.session)
        settings = json.loads(args.settings_json) if args.settings_json else None
        session.process(lambda text: emit('progress', text), transcription_settings=settings)
        emit('complete', '可回看')
        return 0
    except Exception as error:
        traceback.print_exc()
        emit('error', str(error))
        return 1


if __name__ == '__main__':
    sys.exit(main())
