# (AI-assisted) Use upstream's source list, with PS5 objects outside its source tree.
CORE_DIR := src
STATIC_LINKING := 0
HAVE_NTSC := 0
HAVE_HDPACK := 0
WANT_32BPP := 1
include Makefile.common
.PHONY: list
list:
	@printf '%s\n' $(SOURCES_C)
