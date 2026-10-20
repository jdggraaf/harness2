"""Minimal Windows stand-in for the POSIX fcntl.flock used by the upstream JobBench judge."""

import msvcrt

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


def flock(fd, op):
    if op & LOCK_UN:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        msvcrt.locking(fd, msvcrt.LK_NBLCK if op & LOCK_NB else msvcrt.LK_LOCK, 1)
