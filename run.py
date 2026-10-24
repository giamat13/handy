import sys

import window

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == window.WINDOW_FLAG:   # תהליך בן שמציג רק את החלון
        window.show(sys.argv[2])
    else:
        from app import run
        run()
