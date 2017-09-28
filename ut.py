#!/usr/bin/python3

from bs4 import BeautifulSoup
from urllib.request import urlopen, Request
from multiprocessing import cpu_count
import urllib.parse
import http.client
import re, sys, os, getopt, time, pprint, datetime, base64, threading, ssl, socket

class UT(object):
	"""docstring for UT"""

	verbose = False
	quiet = False
	extended = False
	domain = ""
	domains = []
	starturl = None
	logfile = None
	action = 'scan'
	only_static = False
	external_static = False
	list_view = False
	showsummary = False
	deep = None
	threads = cpu_count()+1
	service_threads = 1
	withexternal = False
	withmixed = False

	def read_params(self,mainargs):
		try:
			opts, args = getopt.getopt(mainargs, "hvqsed:t:", ["help","verbose","quiet","diff","only-static","external-static","list","with-external","with-mixed"])
		except getopt.GetoptError as err:
			print(err)
			sys.exit(2)

		for o, a in opts:
			if o in ("-h", "--help"):
				print("Help text coming soon")
				sys.exit()

			elif o in ("-v", "--verbose"):
				self.verbose = True
			elif o in ("-q", "--quiet"):
				self.quiet = True
			elif o in ("-e"):
				self.extended = True
			elif o in ("-s"):
				self.showsummary = True
			elif o in ("-t"):
				self.threads = int(a)
			elif o in ("-d"):
				self.deep = int(a)
			elif o in ("--only-static"):
				self.only_static = True
			elif o in ("--external-static"):
				self.external_static = True
			elif o in ("--with-external"):
				self.withexternal = True
			elif o in ("--with-mixed"):
				self.withmixed = True
			elif o in ("--list"):
				self.list_view = True

			elif o in ("--diff"):
				self.action = "diff"
			else:
				assert False, "unhandled option"

		if self.action == "scan":
			if len(args) > 0:
				self.domain = args[0]
				for u in args:
					d = urllib.parse.urlparse(u)
					if re.search('^http(s)?://', u):
						self.domains.append(d.netloc)
					else:
						self.domains.append(d.path)
				self.domain = self.domains[0]
			else:
				assert False, "wrong input parameters"
		elif self.action == "diff":
			if len(args) > 0:
				self.url = args[0]
		else:
			assert False, "unhandled action"

		global workdir
		workdir = str(os.path.expanduser("~")) + "/.ut/"
		try:
			os.stat(workdir)
		except:
			os.mkdir(workdir)

	def __init__(self, mainargs):
		try:
			self.read_params(mainargs)

			if self.action == "scan":
				self.scan()
			elif self.action == "diff":
				self.diff()
			else:
				assert False, "unhandled action"
		except (SystemExit, BrokenPipeError):
			pass
		except Exception as e:
			raise e
			print(e)

	def log(self,msg=[""],display_it = True):
		if display_it:
			sys.stdout.write("\t".join(msg) + "\n")
			sys.stdout.flush()
		self.logfile.write("\t".join(msg) + "\n")

	def display(self):
		while self.mon_thread_enabled:
			sys.stdout.write("\rTrds: {0:2d}\tQueue: {1:2d}\tSucc: {2:2d}\tSkip: {3:2d}\tExt: {4:3d}\tRedir: {5:2d}\tErr: {6:3d}\tTrb: {7:2d}".format(threading.active_count()-self.service_threads,len(self.queue),len(self.successful),len(self.skipped),len(self.external),len(self.redirected),len(self.errored),len(self.troubled)))
			sys.stdout.flush()
			time.sleep(.5)

	def suredir(self,directory):
		try:
			os.stat(directory)
		except:
			os.mkdir(directory)	   

	def queue_push(self,url,ref,deep):
		self.queue.add(url)
		self.urlmeta[url] = (ref,deep)

	def scan(self):
		global workdir, cachedir, domaindir

		domaindir = workdir + self.domain + "/"
		self.suredir(domaindir)

		cachedir = workdir + self.domain + "/cache/"
		self.suredir(cachedir)

		self.datesuffix = base64.b64encode(time.strftime("%Y-%m-%d %H:%M:%S").encode("ascii"))

		self.urlmeta = {}
		self.queue = set()
		self.known = []
		self.visited = []

		self.successful = []
		self.redirected = []
		self.errored = []
		self.troubled = []

		self.skipped = []
		self.external = []
		self.mixedcontent = []

		for d in self.domains:
			self.queue_push("http://" + d + "/",'',0)
			self.queue_push("https://" + d + "/",'',0)

		self.logfile = open(domaindir + time.strftime("%Y%m%d%H%M%S") + ".log","w")
		if not self.list_view:
			self.log(["Domain: ",self.domain])
			self.log(["Threads: ",str(self.threads)])

		try:
			self.mon_thread_enabled = True
			main_thread = threading.main_thread()
			if self.quiet:
				mon_thread = threading.Thread(target=self.display)
				mon_thread.start()
			self.service_threads = threading.active_count()
			while True:
				while threading.active_count()-self.service_threads < self.threads and len(self.queue) > 0:
					url = self.queue.pop()
					t = threading.Thread(name="Parsing " + url,target=self.chain, args=(url,))
					t.start()

				if len(self.queue) == 0:
					for t in threading.enumerate():
						if t is main_thread:
							continue
						if self.quiet:
							if t is mon_thread:
								continue
						t.join()
					if len(self.queue) == 0:
						break
				else:
					time.sleep(.1)
		except BrokenPipeError:
			pass
		except KeyboardInterrupt:
			sys.stdout.write("\r" + " "*120 + "\rOperation Aborted\n")
			sys.stdout.flush()
		except:
			raise
		finally:
			self.mon_thread_enabled = False
			main_thread = threading.main_thread()
			for t in threading.enumerate():
				if t is main_thread:
					continue
				t.join()

			sys.stdout.write("\r" + " "*120 + "\r" )
			sys.stdout.flush()
			if self.showsummary:
				if len(self.successful):
					self.log()
					self.log(["Success:"])
					for status, reason, url, ref in self.successful:
						self.log([str(status),reason,url,"(Ref:" + ref + ")"])
				if len(self.skipped):
					self.log()
					self.log(["Skipped:"])
					for status, reason, mime, url, ref in self.skipped:
						self.log([str(status),reason,mime,url,"(Ref:" + ref + ")"])
				if len(self.redirected):
					self.log()
					self.log(["Redirected:"])
					for status, reason, url, location, ref in self.redirected:
						self.log([str(status),reason,url,"=> " + location,"(Ref:" + ref + ")"])
				if len(self.errored):
					self.log()
					self.log(["Errored:"])
					for status, reason, url, ref in self.errored:
						self.log([str(status),reason,url,"(Ref:" + ref + ")"])
				if len(self.troubled):
					self.log()
					self.log(["Troubled:"])
					for reason, url, ref in self.troubled:
						self.log([reason,url,"(Ref:" + ref + ")"])
			self.log()
			if len(self.successful):
				self.log(["Success:",str(len(self.successful))])
			if len(self.redirected):
				self.log(["Redirected:",str(len(self.redirected))])
			if len(self.errored):
				self.log(["Errored:",str(len(self.errored))])
			if len(self.troubled):
				self.log(["Troubled:",str(len(self.troubled))])
			if len(self.mixedcontent):
				self.log(["Mixed:",str(len(self.mixedcontent))])
			if len(self.skipped):
				self.log(["Skipped:",str(len(self.skipped))])
			if len(self.external):
				self.log(["External:",str(len(self.external))])

	def chain(self,url):
		try:
			ref, deep = self.urlmeta[url]

			URL = urllib.parse.urlparse(url)

			if not isinstance(URL,urllib.parse.ParseResult):
				return

			url = urllib.parse.urlunparse(URL)

			if url not in self.visited:
				self.visited.append(url)

				if URL.scheme == 'http':
					conn = http.client.HTTPConnection(URL.netloc)
				elif URL.scheme == 'https':
						conn = http.client.HTTPSConnection(URL.netloc)
				else:
					return

				conn.request("GET", URL.path, None, {'User-Agent':'Hadornbot'})
				resp = conn.getresponse()

				if resp.status//100 in (2, ):
					mime = resp.getheader("Content-Type")
					if re.search('^text/html', mime):
						self.successful.append([resp.status,resp.reason,url,ref])
						if not self.quiet and self.verbose:
							self.log([str(resp.status),resp.reason,url,"(Ref:" + ref + ")"])
						html_page = resp.read()
						soup = BeautifulSoup(html_page,'html.parser')
						for link in soup.findAll("a"):
							if self.extended:
								P = urllib.parse.urlparse(link.get('href'))._replace(params='',fragment='')
							else:
								P = urllib.parse.urlparse(link.get('href'))._replace(params='',fragment='',query='')
							if isinstance(P,urllib.parse.ParseResult):
								if P.netloc == '':
									P = P._replace(netloc=URL.netloc)
									res = re.match('\.(/.*)',P.path)
									if res:
										P = P._replace(path=res.group(1))
								if P.scheme == '':
									P = P._replace(scheme=URL.scheme)
								pointer = urllib.parse.urlunparse(P)
								if pointer not in self.visited and pointer not in self.queue:
									external = True
									for d in self.domains:
										if re.search('^(.*\.)?' + d, P.netloc):
											external = False
											if self.deep is None or deep < self.deep:
												self.queue_push(pointer,url,deep+1)
											else:
												if pointer not in self.visited:
													self.visited.append(pointer)
													self.log(["","SKIP",pointer,"(Ref:" + ref + ")"])
									if external:
										if pointer not in self.visited:
											self.visited.append(pointer)
											self.external.append([pointer,ref])
											if not self.quiet and self.withexternal:
												self.log(["","EXT",pointer,"(Ref:" + ref + ")"])
						for img in soup.findAll("img"):
							P = urllib.parse.urlparse(link.get('src'))._replace(params='',fragment='')
							if P.scheme in ('http','https') and P.scheme != URL.scheme:
								pointer = urllib.parse.urlunparse(P)
								self.mixedcontent.append([pointer,ref])
								if not self.quiet and self.withmixed:
									self.log(["","MIX",pointer,"(Ref:" + ref + ")"])

					else:
						self.skipped.append([resp.status,resp.reason,mime,url,ref])
						if not self.quiet and self.verbose:
							self.log([str(resp.status),"NonHTML",url,"(Ref:" + ref + ")"])

				elif resp.status//100 in (3, ):
					location = resp.getheader("Location");
					self.redirected.append([resp.status,resp.reason,url,location,ref])
					self.queue_push(location,url,deep)
					if not self.quiet and self.verbose:
						self.log([str(resp.status),resp.reason,url,"=> " + location,"(Ref:" + ref + ")"])

				elif resp.status//100 in (5, 4, ):
					self.errored.append([resp.status,resp.reason,url,ref])
					if not self.quiet:
						self.log([str(resp.status),resp.reason,url,"(Ref:" + ref + ")"])
				else:
					print(str(resp.status) + "\t" + resp.reason)
					return
		except (KeyboardInterrupt,BrokenPipeError):
			pass
		except (http.client.BadStatusLine, ssl.SSLError, ssl.CertificateError, ConnectionRefusedError, socket.gaierror) as err:
			self.troubled.append([str(err),url,ref])
			if not self.quiet:
				self.log([str(err),url,"(Ref:" + ref + ")"])
		except UnicodeEncodeError:
			print("UnicodeEncodeError: " +URL.netloc + " " + URL.path)
		except:
			raise

if __name__ == "__main__":
	main = UT(sys.argv[1:])
