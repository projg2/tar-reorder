#!/usr/bin/python
#	vim: set fileencoding=utf-8 ts=4 sts=4 sw=4 :
# Simple .tar file reordering script
# (C) 2008-2010 Michał Górny
# Distributed under the terms of the 3-clause BSD license

# XXX:	maybe recognize version-alike extensions?
#		more verbosity levels (light debug)

from optparse import OptionParser

import sys, os, os.path
import tempfile, shutil

import tarfile
import magic

getopt	= OptionParser(
		version		= '0.1.1',
		description	= 'Reorder and group files inside .tar archive by type',
		usage		= 'usage: %prog [options] file1 ( -o outfile | [file2] [...] )'
	)
getopt.add_option('-v', '--verbose', action = 'store_true', dest = 'verbose', default = False,
		help = "Print filenames as they are appended (like 'tar -v')")
getopt.add_option('-m', '--nomagic', action = 'store_false', dest = 'usemagic', default = True,
		help = 'Disable time consuming recognition of filetype using magic')
getopt.add_option('-q', '--quiet', action = 'store_true', dest = 'quiet', default = False,
		help = 'Silence all errors')
getopt.add_option('-d', '--debug', action = 'count', dest = 'debug', default = 0,
		help = 'Increase progress & debugging info level')
getopt.add_option('-o', '--output', dest = 'out',
		help = 'Write reordered .tar to file (instead of replacing the original one)')

(opts, args) = getopt.parse_args()

if len(args) < 1:
	getopt.error('You need to provide at least one tarfile.')
elif len(args) > 1 and opts.out:
	getopt.error('--output can be used with only one input file.')

if opts.usemagic:
	wizard = magic.open(magic.MAGIC_MIME | magic.MAGIC_COMPRESS)
	wizard.load()

class reorder_by:
	type	= 1
	ext		= 2
	name	= 3
	nomore	= 4

reorder_by_descs = [None, 'filetype', 'extensions', 'filenames', 'full paths']

def debug(lv, msg):
	if opts.debug >= lv:
		sys.stderr.write("-*- %s%s\n" % ('\t' * (lv - 1), msg))

def reorder(inlist, crit, intar, outtar, key):
	def copy(flist):
		for f in flist:
			if opts.verbose:
				print f.name

			if f.isreg():
				fc = intar.extractfile(f)
				outtar.addfile(f, fc)
			else:
				outtar.addfile(f)

	out = {}
	before = []
	after = []

	if (len(inlist) <= 1):
		copy(inlist)
		return

	debug(2, 'grouping %d files (%s) by %s ...' % (len(inlist), key, reorder_by_descs[crit]))

	for f in inlist:
		key = None

		if crit == reorder_by.type:
			if not f.isfile():
				if f.isdir():
					before.append(f)
				else: # symlinks & such
					after.append(f)
			else:
				if opts.usemagic:
					fc = intar.extractfile(f)
					key = wizard.buffer(fc.read(4096))

				if key is None: # (or not opts.usemagic) implied
					key = ''

		if crit == reorder_by.ext:
			exts = []
			name = f.name
			while 1:
				tmp = os.path.splitext(name)
				name = tmp[0]
				ext = tmp[1]
				if (ext):
					exts.append(ext)
				else:
					break

			# NOTE: we really want them reversed, so that .tar.bz2 go near other .bz2, etc.
			key = ''.join(exts)

		if crit == reorder_by.name:
			key	= os.path.split(f.name)[1]

		if crit == reorder_by.nomore:
			before.append(f)

		if key is not None:
			if not key in out.keys():
				out[key] = []
			out[key].append(f)

	debug(3, '... got %d files in before, %d in after and %d in %d groups' % (len(before), len(after),
			len(inlist) - len(before) - len(after), len(out.keys())))

	before.sort()
	after.sort()

	copy(before)
	for k in sorted(out.keys()):
		reorder(out[k], crit + 1, intar, outtar, k)
	copy(after)

processed = 0

for fn in args:
	debug(1, 'processing %s' % fn)
	try:
		def getRealDir(path):
			if os.path.islink(path):
				path = os.path.join(os.path.dirname(path), os.readlink(path))
			return os.path.dirname(path)

		# workaround for failpython bug
		# something (tarfile? magic?) is replacing fd0 with pipe
		# so make sure fd0 is nothing important
		tmpipe = os.pipe()

		if not opts.out:
			tmpf = tempfile.NamedTemporaryFile(dir = getRealDir(fn), delete = False)
			tmpfn = tmpf.name
			debug(2, 'tempfile: %s' % tmpfn)
		else:
			tmpfn = opts.out

		try:
			intar = tarfile.open(fn)
			if opts.out:
				outtar = tarfile.open(tmpfn, mode = 'w')
			else:
				outtar = tarfile.open(fileobj = tmpf, mode = 'w')
		except:
			if not opts.out:
				os.unlink(tmpfn)
			raise

		try: # not critical
			os.close(tmpipe[0])
			os.close(tmpipe[1])
		except:
			pass

		try:
			reorder(intar.getmembers(), reorder_by.type, intar, outtar, '*all*')
		except:
			os.unlink(tmpfn)
			raise
		else:
			if opts.out:
				debug(1, 'reorder finished, output written to %s' % tmpfn)
			else:
				debug(1, 'reorder finished, replacing %s' % fn)

		intar.close()
		outtar.close()

		if not opts.out:
			tmpf.close()
			shutil.move(tmpfn, fn)
	except IOError as e:
		if not opts.quiet:
			sys.stderr.write("Unable to reorder file '%s', details below:\n\t%s\n" % (fn, str(e)))
	except tarfile.ReadError:
		if not opts.quiet:
			sys.stderr.write("Unable to reorder file '%s', open as tarfile failed.\n" % fn)
	else:
		processed += 1

if processed != len(args):
	if not opts.quiet:
		if processed == 0:
			sys.stderr.write('No files were processed successfully.\n')
		else:
			sys.stderr.write('%d of %d files were processed successfully.\n' % (processed, len(args)))
	sys.exit(1)

sys.exit(0)
