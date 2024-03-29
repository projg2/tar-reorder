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
try:
	import magic
except ImportError:
	have_magic = False
else:
	have_magic = True

getopt = OptionParser(
		version		= '0.2',
		description	= 'Reorder and group files inside .tar archive by type',
		usage		= 'usage: %prog [options] file1.tar ( -o outfile.tar | [file2.tar] [...] )'
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
	if have_magic:
		wizard = magic.open(magic.MAGIC_MIME | magic.MAGIC_COMPRESS)
		wizard.load()
	else:
		sys.stderr.write("Unable to import 'magic' module, assuming --nomagic.\n")
		opts.usemagic = False

class reorder_by:
	type	= 1
	ext		= 2
	name	= 3
	last	= 4

reorder_by_descs = [None, 'filetype', 'extensions', 'filenames', 'full paths']

def debug(lv, msg):
	""" Output debug message if debuglevel is appropriate. """
	if opts.debug >= lv:
		sys.stderr.write("-*- %s%s\n" % ('\t' * (lv - 1), msg))

def reorder(inlist, crit, intar, outtar, key):
	""" Perform the reorder of files in 'inlist' using criteria 'crit'. """
	def copy(flist):
		""" Copy files in 'flist' into new tarball. """
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
				(name, ext) = os.path.splitext(name)
				if ext:
					exts.append(ext)
				else:
					break

			# NOTE: we indeed do get the extension list reversed
			# (i.e. '.tar.bz2' comes as '.bz2.tar') and it is fine
			# this way we keep '.bz2's near other '.bz2's etc.
			key = ''.join(exts)

		if crit == reorder_by.name:
			key	= os.path.split(f.name)[1]

		if crit == reorder_by.last:
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

		# * Workaround for Python bug *
		# Something braindead (magic?) is replacing fd0 with pipe and then
		# closing it, leaving us with empty fd0. If we open the tarfile then,
		# it gets into fd0 and is replaced with mentioned pipe.
		# Thus, we open a stray pipe to fill in the gap and make sure that
		# important fds get higher numbers.
		tmpipe = os.pipe()

		intar = tarfile.open(fn)
		infmt = intar.format
		inenc = intar.encoding
		incls = intar.fileobj.__class__

		if not opts.out:
			tmpf = tempfile.NamedTemporaryFile(dir = getRealDir(fn), delete = False)
			tmpfn = tmpf.name
			debug(2, 'tempfile: %s' % tmpfn)

			if incls is not file:
				# sorry, bz2 doesn't like chaining, we need to open by fn
				keepf = tmpf
				tmpf = incls(tmpfn, 'wb')
				keepf.close()
		else:
			# XXX: let user choose compression
			tmpfn = opts.out
			tmpf = incls(tmpfn, 'wb')
		debug(2, 'using %s for output' % str(incls))

		try:
			outtar = tarfile.open(fileobj = tmpf, mode = 'w', format = infmt, encoding = inenc)

			try: # not critical
				os.close(tmpipe[0])
				os.close(tmpipe[1])
			except:
				pass

			try:
				reorder(intar.getmembers(), reorder_by.type, intar, outtar, '*all*')
			except:
				outtar.close()
				raise
		except:
			tmpf.close()
			os.unlink(tmpfn)
			intar.close()
			raise
		else:
			if opts.out:
				debug(1, 'reorder finished, output written to %s' % tmpfn)
			else:
				debug(1, 'reorder finished, replacing %s' % fn)

		intar.close()
		outtar.close()

		tmpf.close()
		if not opts.out:
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
