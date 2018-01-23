#!/usr/bin/env python3
# coding: utf-8
# authors/licensing {{{

# @author: Iain McDonald
# Contributors: Jef Treece, Harald Alvestrand, Zak Jones
# Purpose: Reduction and comparison script for Y-chromosome NGS test data
# For free distribution under the terms of the GNU General Public License,
# version 3 (29 June 2007)
# https://www.gnu.org/licenses/gpl.html

# run this script as a command with no args to execute some tests

# }}}
# libs {{{

import os,yaml,shutil,glob,re,csv,zipfile,subprocess
from db import DB
from collections import defaultdict

# }}}

REDUX_CONF = 'config.yaml'
config = yaml.load(open(REDUX_CONF))

import sys
sys.path.insert(0, config['REDUX_ENV'])


# routines - debug
# fixme - there are too many levels of verbosity - probably should be a bitmap/flags
# fixme - level is ignored
# fixme - stdout or stderr?
def trace (level, msg):
    print(msg)
    #if level <= config['verbosity']:
    #    print(msg)
    #TODO: below line in clades.py
    #sys.stderr(flush)


# return a path to a file or directory in the configured data dir
def data_path(fname):
    return os.path.join(config['REDUX_DATA'], fname)

def refresh_dir(DIR,cleanFlag=False):
    DIR = os.path.join(config['REDUX_ENV'], DIR)
    #print DIR
    if (os.path.isdir(DIR)):
        files = glob.glob(DIR+'/*')
        if cleanFlag:
            for f in files:
                os.remove(f)
    else:
        os.makedirs(DIR)

# update the mtime of a file without changing file contents
def touch_file(FILE):
    if os.path.exists(FILE):
        open(FILE,'a').close()

def cmd_exists(CMD):
    return any(os.access(os.path.join(path, CMD), os.X_OK) for path in os.environ["PATH"].split(os.pathsep))


# various scratch/data directory setup under "data"
def setup_dirs():
    shutil.rmtree(data_path(config['unzip_dir']),ignore_errors=True)
    os.makedirs(data_path(config['unzip_dir']))

# it may make sense to pull this out into a separate file, import (unpack-zip-files)
# Jef
def extract_zips():
    if not os.path.isdir(data_path(config['zip_dir'])):
        trace (0, '   Warn: no directory with zip files: %s' % config['zip_dir'])
        return []

    FILES = os.listdir(data_path(config['zip_dir']))

    # try to parse out at least the kit number by trying a series of regular expressions
    # adding regular expressions at the end of this list is safer than at the beginning
    # order is important - rules at top are matched first

    # constants used in filename regular expressions
    # groupings (?:xxx) are ignored

    ws = r'^[_]?'
    nam1 = r"[a-z]{0,20}|O\&#39;[a-z]{3,20}|O['][a-z]{3,20}"
    cname = r'([\w]{1,20})' #matches unicode chars; also matches digits though
    pnam = r'\('+nam1+r'\)'
    nam2 = r'(?:' +nam1 +'|' +pnam +r')'
    ndate = r'(?:(201[1-8][\d]{4}|201[1-8]-\d\d-\d\d|\d{4}201[1-8]))'
    sep = r'[\-\s\._]'
    seps = r'[\-\s\._]?'
    # sepp = r'[\-\s\._]+'
    sepp = r'_' # only use underscore as field separator
    sept = r'[\-\s\._]{3}'
    bigy = r'(?:big' +seps+ r'y(?:data)?|ydna)'
    rslt = r'(?:results|data|rawdata|vcfdata|raw data|csvexport|raw_data|raw|bigyrawdata)'
    name = r'((?:'+nam2+seps+'){1,3})'
    kit = r'(?:(?:kit|ftdna)?[ #]?)?([enhb1-9][0-9]{3,6})'
    rzip = r'zip(?:.zip)?'
    plac = r'([A-Z]{2})'

    #0 e.g. bigy-Treece-N4826.zip
    #1 e.g. N4826_Treece_US_BigY_RawData_2018-01-03.zip
    #2 e.g. 548872_Lindstrom_Germany_BigY_RawData_2018-01-01.zip

    name_re = [
        (re.compile(ws+sep.join([bigy,name,kit,rzip]), re.I), 'name', 'kit'),
        (re.compile(ws +sepp.join([kit,name,plac,bigy,rslt,ndate])+'.zip', re.I), 'kit', 'name'),
        (re.compile(ws +sepp.join([kit,cname,plac,bigy,rslt,ndate])+'.zip', re.I), 'kit', 'name')
        ]


    trace (25, '   File names mapped, according to which regular expression:')
    # track counts - only for diagnostics
    cnt = defaultdict(int)
    # list of non-matching files
    nomatch=[]
    # all of the file names we could parse
    fname_dict = {}
    
    for line in FILES:
        fname = line.strip()
        if fname in rename_dict:
            # hand-edited filename mappings
            kkit, nname = rename_dict[fname]
            fname_dict[fname] = kkit, nname
            trace(25, '     {3:>2} {0:<50s}{1:<15s}{2:<10s}'.format(fname, nname, kkit, 'd'))
            cnt['d'] += 1
        else:
            if fname[-4:] not in ('.gitignore'):
                if fname[-4:] not in ('.zip'):
                    trace (15, '   Found foreigner hanging out in zip directory: {0}'.format(fname))
                continue
            d = {}
            for ii, (r,k1,k2) in enumerate(name_re):
                s = r.search(line)
                if s:
                    d[k1] = s.groups()[0]
                    if k2:
                        d[k2] = s.groups()[1]
                    else:
                        d['name'] = 'Unknown'
                    try:
                        trace (25, '     {3:>2} {0:<50s}{1:<15s}{2:<10s}'.format(fname,
                                                   d['name'], d['kit'], ii))
                        cnt[ii] += 1
                        fname_dict[fname] = d['kit'], d['name']
                    except:
                        trace (1, '   FAILURE on filename:', fname)
                    break
            else:
                if line not in ('.gitignore'):
                    nomatch.append(line)

    trace (20, '   Number of filenames not matched: {0}'.format(len(nomatch)))
    trace (22, '   Which expressions were matched:')
    for nn,cc in cnt.items():
        trace (22, '     {0:>2}: {1:>4}'.format(nn,cc))

    if len(nomatch) > 0:
        trace (10, '   Files that did not match:')
        for ll in nomatch:
            if ll.strip() not in ('.gitignore'):
                trace (10, '    %s' % ll.strip())
            else:
                nomatch = nomatch - 1

    # keep track of what needs to be cleaned up
    emptydirs = []

    for fname in fname_dict:
        kitnumber, kitname = fname_dict[fname]
        try:
            zf = zipfile.ZipFile(os.path.join(config['REDUX_ENV'], 'zip_dir', fname))
        except:
            trace (1, '   ERROR: file %s is not a zip' % fname)
            sys.exit()
        listfiles = zf.namelist()
        bedfile = vcffile = None
        for ff in listfiles:
            dirname, basename = os.path.split(ff)
            if basename == 'regions.bed':
                bedfile = ff
            elif basename == 'variants.vcf':
                vcffile = ff
            if dirname and (dirname not in emptydirs):
                emptydirs.append(dirname)
        if (not bedfile) or (not vcffile):
            trace(1, '   Warn: missing data in '+fname)
            continue
        if (bedfile == None) ^ (vcffile == None):
            trace(1, '   Warn: BED or VCF file is missing for %s' % fname)
            trace(1, '   This is an unexpected error. %s not processed.' % fname)
            continue
        zf.extractall(config['unzip_dir'], [bedfile, vcffile])
        base = '%s-%s' % (kitname, kitnumber)
        try:
            fpath = os.path.join(config['unzip_dir'], '%s')
            trace (40, "      "+fpath % base)
            os.rename(fpath % bedfile, (fpath % base)+'.bed')
            os.rename(fpath % vcffile, (fpath % base)+'.vcf')
        except:
            trace(1, '   Warn: could not identify VCF and/or BED file for '+base)

    # clean up any empty dirs unzip created

    if emptydirs:
        trace (30, '   Trying to remove droppings:')
        for dir in emptydirs:
            try:
                dp = os.path.join(config['unzip_dir'], dir)
                os.removedirs(dp)
                trace (30, '     {0}'.format(dp))
            except FileNotFoundError:
                pass
            except:
                trace (30, '     W! could not remove {0}'.format(dp))
                pass

    # list of file names we unzipped

    files = os.listdir(data_path(config['unzip_dir']))
    return files
    
# unpacks all of the zip files in zip_dir and puts the results in unzip_dir
# todo - we need to be able to be selective about which files to unpack
def unpack():
    # collect run time statistics

    trace(10,'   Running the unpack-zip script...')
    refresh_dir(data_path(config['unzip_dir']),cleanFlag=False)
    # fixme - interop with API from DW
    fnames = extract_zips()
    trace (10, '   Number of files: {0}'.format(len(fnames)))
    trace (40, '   Files unpacked:')
    for ff in fnames:
        trace (40, ff)

# I don't know what this procedure is for; it looks like it needs to go in the
# main loop
def skip_to_Hg19(dbo):

    # skip to <= 1 - unpack zips

    if (config['skip_to'] <= 1):
        trace (2, "Unpacking ZIP files...")
        #unpack(REDUX_ENV+'/'+config['zip_dir'],REDUX_ENV+'/'+config['unzip_dir'],config['verbosity'])
        unpack()
        t = float((time.clock() - start_time))
        trace(10, '   ...complete after %.3f seconds' % t)
        trace (5, "Associating unzipped files with kits...")
        
    # skip to <= 10 - associate kits with people

    if (config['skip_to'] <= 10):
        trace (2, "Associating kits with people...")
        
    # skip to <= 11 - generate dictionary of variant positions 

    #   The VCF files are parsed twice. The first pass identifies the list
    #   of variants to be queried. The second pass reads the calls for those
    #   variants. This means we only need to treat positions with a variant,
    #   rather than every position in a chromosome.
    #   Using a dictionary here means only one copy of each variant is
    #   created.

    if (config['skip_to'] <= 11):

        #vcffiles

        trace (2, "Generating database of all variants...")
        # fixme - populate dataset
        vcffiles = [f for f in os.listdir(os.path.join(config['REDUX_ENV'], config['unzip_dir'])) if f.endswith('.vcf')]
        trace (10, "   %i files detected" % len(vcffiles))
        
        #variant_dict

        #print(REDUX_ENV)
        variant_dict = {}
        for file in vcffiles:
            # fixme - this should come from walking through dataset
            vcf_calls = readHg19Vcf(os.path.join(config['REDUX_ENV'], config['unzip_dir'], file))
            # fixme .update is probably a slow way
            variant_dict.update(vcf_calls)

        trace (10, "   %i variants found" % len(variant_dict))
        t = float((time.clock() - start_time))
        trace(10, '   ...complete after %.3f seconds' % t)

        # dump variant dict into sorted array

        trace (20, "   Dumping variants into array...")
        variant_array = np.array(list(variant_dict.values()))

        # variant_array = np.array([],dtype={'names': ('start', 'anc', 'der'),'formats': ('i4', 'S20', 'S20')})

        trace (30, "      Check variant [0] is %s" % variant_array[0])
        trace (30, "      Check variant [0] position is %s" % variant_array[0][1])
        trace (30, "      Check variant [%s] is %s" % (len(variant_dict)-1, variant_array[len(variant_dict)-1]))
        trace (30, "      Check variant [%s] position is %s" % (len(variant_dict)-1, variant_array[len(variant_dict)-1][1]))

        #db calls

        trace (20, "   Inserting data into variant array database...")
        dbo.insert_variants(variant_array, 'hg38')
        t = float((time.clock() - start_time))
        trace(10, '   ...complete after %.3f seconds' % t)
        
    # skip to <= 12 - reading calls for variants
    
    #db calls
    
    if (config['skip_to'] <= 12):
        trace (2, "Generating database of calls...")
        vcffiles = [f for f in os.listdir(os.path.join(config['REDUX_ENV'], config['unzip_dir'])) if f.endswith('.vcf')]
        trace (10, "   %i files detected" % len(vcffiles))
        # dbo.insert_calls()

    # skip to <= 13 - name variants and derive ancestral values

    # Some variants are positive in the reference sequence, so we need to
    # look up their ancestral values. We'll get the SNP names while we're
    # at it.

    #db calls

    if (config['skip_to'] <= 13):
        # Read in SNPs from reference lists
        trace (2, "Getting names of variants...")
        trace (10, "   Importing SNP reference lists...")



        # db work - how we doing? {{{

        # Read in SNPs from reference lists
        # Probably doesn't need to be done at this point
        # trace (10, "   Joining reference lists to variant database...")

        # self.dc.execute('''SELECT hg38.grch38, hg38.name
        # FROM hg38
        # INNER JOIN hg19 on hg19.name = hg38.name''')

        # self.dc.execute('''SELECT variants.id, hg38.name
        # FROM variants
        # LEFT OUTER JOIN hg38 on hg38.grch38 = variants.id''')

        # }}}

        t = float((time.clock() - start_time))
        trace(10, '   ...complete after %.3f seconds' % t)
            
    #commit

    dbo.commit()

    # Print final message and exit {{{{

    t = float((time.clock() - start_time))
    trace (1, "Execution finished in: %.3f seconds" % t)

    # }}}

# routines - arghandler (redux1) - Zak

def go_all():
    go_backup()
    go_prep()
    go_db()
    
# cache previous run's results
def go_backup():

    trace(0,"** performing backup.")
    trace(0,"** (msg) CREATING BACKUP COPIES OF EXISTING FILES...")
    
    # autobackup dir
    refresh_dir('autobackup')
    for FILE_PATTERN in config['backup_files'].split():
        for FILE in glob.glob(FILE_PATTERN):
            shutil.copy(FILE,'autobackup')
    
    # autobackup2 dir {{{

    # Make further backup copies when running the script from scratch
    # This is useful when you want to make changes to the bad/inconsistent list, but still want to compare to the original previous run.
    # For example:
    # gawk 'NR==FNR {c[$5]++;next};c[$5]==0' tree.txt autobackup2/tree.txt
    # will tell you the changes to the tree structure that have resulted from the addition of new kits between "from-scratch" runs.
    
    #refresh_dir('autobackup2')
    #for FILE_PATTERN in config['backup_files'].split():
    #    for FILE in glob.glob(FILE_PATTERN):
    #        shutil.copy(FILE, 'autobackup2')
    
    # }}}
    
    if config['make_report']:
        #print "MAKING REPORT..."
        delete_file('report.csv')
    
    trace(0,"** + backup done.")
    

# I'm not sure what this procedure is for ???
def go_prep():

    trace(0,"** prepare file structure.")

    # SKIPZIP check (beg)

    if not config['skip_zip']:

        # Check ZIPDIR - contains existing zip files {{{

        if not os.path.exists(config['zip_dir']):
            trace(0,"Input zip folder does not appear to exist. Aborting.\n")
            sys.exit()

        # }}}
        # Check WORKING - the zip working exists && Empty it, otherwise make it {{{

        refresh_dir('working')

    # }}}
        # Check UNZIPDIR - contains zip output; refresh it {{{

        refresh_dir('unzips',not config['zip_update_only'])

        # }}}
        # Get the list of input files {{{

        FILES = glob.glob(os.path.join(config['REDUX_ENV'], 'zips', 'bigy-*.zip'))

        if len(FILES) == 0:
            trace(0,"No input files detected in zip folder. Aborting.")
            trace(0,"Check name format: should be bigy-<NAME>-<NUMBER>.zip\n")
            sys.exit()
        else:
            trace(0,"input files detected: " + str(FILES))

        # }}}
        # Check whether unzip is installed {{{

        if not cmd_exists('unzip'):
            trace(0,"Unzip package not found. Aborting.")
            sys.exit()

        # }}}
        # Check whether SNP list exists {{{

        csv = os.path.join(config['REDUX_DATA'], config['b38_snp_file'])
        if not os.path.exists(csv):
            trace(0,"SNP names file does not exist. Try:")
            trace(0,"wget http://ybrowse.org/gbrowse2/gff/"+csv+" -O "+csv+"\n")
            sys.exit()

        # }}}
        # Check whether merge-ignore list exists {{{

        touch_file('merge-ignore.txt')

        # }}}
     
        # fix bash code (beg)

        # Unzip each zip in turn {{{

        trace(0,"Unzipping...")

        if config['zip_update_only']:
            #FILES=(`diff <(ls zip/bigy-*.zip | sed 's/zip\/bigy-//' | sed 's/.zip//') <(ls unzip/*.vcf | sed 's/unzip\///' | sed 's/.vcf//') | grep '<' | awk '{print "zip/bigy-"$2".zip"}'`)
            SET = [set(re.sub('zip/bigy-','',re.sub('.zip','',S)) for S in glob.glob('zips/bigy-*.zip'))]-set([re.sub('bigy-','',S) for S in glob.glob('unzips/*.vcf')])
            #print  ${#FILES[@]} "new files found"
            trace(0,"new files found: "+len(SET))
            trace(0,"new files detected: " + list(SET))

        #FILECOUNT=0

        #for ZIPFILE in ${FILES[@]}; do

        #    let FILECOUNT+=1
        #    PREFIX=`echo "$ZIPFILE" | gawk -F- '{print $2"-"$3}' | sed 's/.zip//'`
        #    #echo $FILECOUNT: $ZIPFILE : $PREFIX
        #    unzip -q $ZIPFILE -d working/
        #    if [ -s working/*.vcf ]; then mv working/*.vcf working/"$PREFIX".vcf; fi
        #    if [ -s working/*.bed ]; then mv working/*.bed working/"$PREFIX".bed; fi
        #    if [ -s working/*/variants.vcf ]; then mv working/*/variants.vcf working/"$PREFIX".vcf; fi
        #    if [ -s working/*/regions.bed ]; then mv working/*/regions.bed working/"$PREFIX".bed; fi
        #    if [ -s working/"$PREFIX".vcf ] && [ -s working/"$PREFIX".bed ]; then
        #        mv working/"$PREFIX".vcf unzip/;
	#	mv working/"$PREFIX".bed unzip/;
        #    else echo ""; echo "Warning: could not identify VCF and/or BED file for $PREFIX"
        #    fi

        #    rm -r working; mkdir working
        #    echo -n "."

        #done

        #echo ""

        # }}}

        # fix bash code (end)
    #fi

    # SKIPZIP check (end)

    # fix bash code (beg)

    # Skip some more if SKIPZIP set {{{

    #if config['skip_zip'] > 1:
    #    cp header.csv report.csv
    #    NFILES=`head -1 header.csv | gawk -v FS=, '{print NF-17}'`
    #    echo "... $NFILES results to be post-processed"

    #if config['skip_zip'] < 1:
    #    # Check number of BED = number of VCF files
    #    if [ `ls unzip/*.bed | wc -l` != `ls unzip/*.vcf | wc -l` ]; then
    #    echo "Number of BED files does not equal number of VCF files."
    #    echo "This is an unexpected error. Aborting."
    #    sys.exit()

    #T1=`date +%s.%N`
    #DT=`echo "$T1" "$T0" | gawk '{print $1-$2}'`
    #echo "...complete after $DT seconds"

    # }}}
    # Generate statistics from BED & VCF files {{{

    #echo "Generating preliminary statistics..."

    #FILES=(`ls unzip/*.bed`)
    #echo "Total Kits:,,,,,"${#FILES[@]}',,,,,,,,,,,Kit' > header.csv
    #echo 'KEY:,,,,,,,,,,,,,,,,Date' >> header.csv
    #echo 'N+/N-,Number of +/- calls,,,,,,,,,,,,,,,Coverage' >> header.csv
    #echo '(?+),Call uncertain but presumed positive,(position forced),,,,,,,,,,,,,,...for age analysis' >> header.csv
    #echo 'cbl,Occurs on lower boundary of coverage,(often problematic),,,,,,,,,,,,,,Regions' >> header.csv
    #echo 'cbu,Occurs on upper boundary of coverage,(usually ok),,,,,,,,,,,,,,Variants' >> header.csv
    #echo 'cblu,Occurs as a 1-base-pair region,,,,,,,,,,,,,,,Passed' >> header.csv
    #echo '1stCol,First column which is positive,,,,,,,,,,,,,,,Simple SNPs' >> header.csv
    #echo 'Recur,Recurrencies in tree,(check: 1 or (R)),,,,,,,,,,,,,,SNPs under' "$TOPSNP" >> header.csv
    #echo '(s?),Questionable singleton,(not negative in some clademates),,,,,,,,,,,,,,Singleton SNPs' >> header.csv
    #echo '(s?!),Questionable singleton,(not negative in all clademates),,,,,,,,,,,,,,...for age analysis' >> header.csv
    #echo '(R),Allowed recurrency,,,,,,,,,,,,,,,Indels' >> header.csv
    #echo 'Blank,Securely called negative,,,,,,,,,,,,,,,Indels under' "$TOPSNP" >> header.csv
    #echo 'Full report at:,www.jb.man.ac.uk/~mcdonald/genetics/report.csv,,,,,,,,,,,,,,,Singleton Indels' >> header.csv
    #echo 'Non-shared SNPs' >> header.csv
    #echo 'GrCh37,Name(s),Ref,Alt,Type,N+,(?+),N-,nc,cbl+,cbl-,cbu+,cbu-,cblu+,cblu-,1stCol,Recur' >> header.csv
    #echo "Generating statistics for" ${#FILES[@]} "BED files..."
    #echo -n '[1/5] '
    #KITNAMES=`ls unzip/*.bed | sed 's/unzip\///g' | sed 's/.bed//g' | awk '1' ORS=,`
    #echo -n '[2/5] '
    #KITDATES=`ls -l --time-style +%Y-%m-%d unzip/*.bed | cut -d\  -f6 | awk '{print}' ORS=,`
    #echo -n '[3/5] '
    #STATS1=`gawk 'NR==FNR {a[NR]=$2;b[NR]=$3;n=NR} FNR==1 && NR!=1 {if (nfiles>0) print s,as,nrf;s=as=0;nfiles++} NR!=FNR {s+=$3-$2; for (i=1;i<=n;i++) if ($2<=b[i] && $3>=a[i]) {x=($3>b[i]?b[i]:$3)-($2>a[i]?$2:a[i]); if (x<0) x=0; as+=x}} {nrf=FNR} END {print s,as,FNR}' age.bed unzip/*.bed`
    #echo -n '[4/5] '
    #STATS2=`gawk '$1=="chrY" {n++} $1=="chrY" && $7=="PASS" {v++; if ($4!="." && $5!=".") {if (length($4)==1 && length($5)==1) {s++} else {i++} }} FNR==1 && NR!=1 {print n,v,s,0,0,0,i,0,0; n=v=s=i=0} END {print n,v,s,0,0,0,i,0,0}' unzip/*.vcf`

    #echo -n '[5/5] '
    #echo "$KITNAMES" | awk '{print substr($0,1,length($0)-1)}' > foo
    #echo "$KITDATES" | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS1" | awk '{print $1}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS1" | awk '{print $2}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS1" | awk '{print $3}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS2" | awk '{print $1}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS2" | awk '{print $2}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS2" | awk '{print $3}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS2" | awk '{print $4}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS2" | awk '{print $5}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS2" | awk '{print $6}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS2" | awk '{print $7}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS2" | awk '{print $8}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #echo "$STATS2" | awk '{print $9}' ORS=, | awk '{print substr($0,1,length($0)-1)}' >> foo
    #paste header.csv foo | sed 's/\t/,/' > fubar
    #mv fubar header.csv

    ## This does the same thing, but slower. From version 0.6.1
    ## for BEDFILE in ${FILES[@]}; do
    ##	VCFFILE=`echo "$BEDFILE" | sed 's/.bed/.vcf/'`
    ##	KITNAME=`echo "$BEDFILE" | gawk -F/ '{print $2}' | sed 's/.bed//'`
    ##	KITDATE=`ls -l --time-style +%Y-%m-%d "$BEDFILE" | cut -d\  -f6`
    ##	STATS=`gawk 'NR==FNR {a[NR]=$1;b[NR]=$2;n=NR} NR!=FNR {s+=$3-$2-; for (i=1;i<=n;i++) if ($2<=b[i] && $3>=a[i]) {x=($3>b[i]?b[i]:$3)-($2>a[i]?$2:a[i]); if (x<0) x=0; as+=x}} END {print s,as,FNR}' age.bed "$BEDFILE"`
    ##	STATS2=`gawk '$1=="chrY" {n++} $1=="chrY" && $7=="PASS" {v++; if ($4!="." && $5!=".") {if (length($4)==1 && length($5)==1) {s++} else {i++} }} END {print n,v,s,0,0,0,i,0,0}' "$VCFFILE"`
    ##	STATS="$KITNAME $KITDATE $STATS $STATS2"
    ##	gawk -v s="$STATS" 'NR==1 {split(s,stat," ")} {print $0","stat[NR]}' header.csv > foo
    ##	mv foo header.csv
    ##	echo -n "."
    ##done

    #echo ""
    #cp header.csv report.csv

    #T1=`date +%s.%N`
    #DT=`echo "$T1" "$T0" | gawk '{print $1-$2}'`
    #echo "...complete after $DT seconds"

    # Close SKIPZIP if

    #fi

    # }}}
    # Skip some more if SKIPZIP set {{{

    #if [ "$SKIPZIP" == "0" ]; then

    # }}}
    # Identify list of variants {{{

    #echo "Identifying list of variants..."
    #gawk '$1=="chrY" && $7=="PASS" && $4!="." && $5!="." {print $2"\t"$4"\t"$5}' unzip/*.vcf | sed 's/,/;/g' > variant-list.txt

    #rm -f variant-list.txt
    #for BEDFILE in ${FILES[@]}; do
    #	VCFFILE=`echo "$BEDFILE" | sed 's/.bed/.vcf/'`
    #	gawk '$1=="chrY" && $7=="PASS" && $4!="." && $5!="." {print $2"\t"$4"\t"$5}' "$VCFFILE" | sed 's/,/;/g' >> variant-list.txt
    #	echo -n "."
    #done
    #echo ""

    # }}}
    # Add "missing" clades from file {{{

    # ! marks the implication so that is not counted when the SNP counts are made in the next section

    #gawk '$1=="^" {print $2"\t"$4"\t"$5"\t!"}' implications.txt >> variant-list.txt

    # }}}
    # Create a unique list of variants {{{

    #sort -nk1 variant-list.txt | uniq -c | sort -nk2 | gawk '{n="SNP"} $5=="!" {$1=0} length($3)>1 || length($4)>1 {n="Indel"} {print $2",,"$3","$4","n","$1",,,,,,,,,,,"}' > foo; mv foo variant-list.txt

    #T1=`date +%s.%N`
    #DT=`echo "$T1" "$T0" | gawk '{print $1-$2}'`
    #print "...complete after $DT seconds"

    # }}}
    # Write out positive cases {{{

    #echo "Identifying positives and no calls..."

    # }}}
    # Include python script by Harald A. {{{

    #./positives-and-no-calls.py ${FILES[@]} > variant-match.txt

    #T1=`date +%s.%N`
    #DT=`echo "$T1" "$T0" | gawk '{print $1-$2}'`
    #print "...complete after $DT seconds"

    # }}}

    # fix bash code (end)

    trace(0,"** + prep done.")
    

# routines - arghandler (redux2) - Zak

# utility procuedure to drop/create the database and schema
def go_db():
    trace(1, "Initialising database...")
    dbo = DB()
    dbo.create_schema()
    return dbo


#    skip_to_Hg19(dbo)


# import vcf hg38

#note: it looks like clades.py is doing something like this for hg19
def getH38references():
    foo = 1

#note: sample code for calling this awk script
def getVCFvariants(FILE):
    cmd = "getVCFvariants.sh"
    p = subprocess.Popen(cmd, FILE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout, stderr = p.communicate()

#routines - "arghandler" (sort prototype) - Zak

# I'm not sure what this procedure is for
def go_sort_db():
    #trace(0,"** process SNP data.")
    dbo = go_db()
    dbo.insert_sample_sort_data()
    #dbo.commit()
    dbo.sort_data()
    #trace(0,"** + SNP processing done.")

#routines - "arghandler" (new v2 schema)- Jef/Zak

# SNP extraction routines based on original - Harald 
# extracts the SNP calls from the VCF files and
# determines the coverage of SNPs in the BED files of BigY tests.
def analyzeVcf(file):

    #Returns a dict of position -> mutation mappings

    with open(os.path.splitext(file)[0] + '.vcf') as vcffile:
        trace (30, "   Extracting VCF: %s" % vcffile)
        result = {}
        for line in vcffile:
            fields = line.split()
            if (fields[0] == 'chrY' and fields[6] == 'PASS' and fields[3] != '.' and fields[4] != '.'):
                # fix by Jef Treece for fields containing commas:
                result[int(fields[1])] = fields[1] + '.' + fields[3].replace(',', ';') + '.' + fields[4].replace(',', ';')
                # result[int(fields[1])] = fields[1] + '.' + fields[3] + '.' + fields[4]
        return result
    
def analyzeBed(file):

    #Returns an array of path segments.

    with open(os.path.splitext(file)[0] + '.bed') as bedfile:
        trace (30, "   Extracting BED: %s" % bedfile)
        result = []
        for line in bedfile:
            fields = line.split()
            if (fields[0] == 'chrY'):
                result.append((int(fields[1]), int(fields[2])))
        return result
    
def makeCall(pos, index_container, bed_calls):

    #Figure out whether this position is on a segment boundary.
    #Between segments = 'nc'; top of segment = 'cbu'; bottom of segment = 'cbl'.
    #Only call in a single-position segment = 'cblu'.
    #index_container contains first segment to be looked at.
    #This function must only be called for increasing values of pos, and with
    #sorted bed_calls.

    call = ';nc'
    for bed_index in range(index_container[0], len(bed_calls)):
        pos_pair = bed_calls[bed_index]
        index_container[0] = bed_index
        if pos_pair[1] >= pos:
            # Position is before or within this segment.
            if pos_pair[0] <= pos:
                # Position is within this segment.
                if pos_pair[0] == pos_pair[1] and pos_pair[0] == pos:
                    call = ';cblu'
                elif pos_pair[0] == pos:
                    call = ';cbl'
            elif pos_pair[1] == pos:
                call = ';cbu'
            else:
                call = ''
        else:
            # Position is before this segment.
            call = ';nc'
        return call
        # If position is after segment, continue.
    return ';nc' # After end of last segment.
    
def extract(unzip_dir,files,variants):

    d = []
    s = []

    curpath = os.path.abspath(os.curdir)
    with open(os.path.join(curpath, 'variant-list.txt')) as line_headings:
        for line in line_headings:
            d.append(line.rstrip())
            x = line.split(',')
            s.append(int(x[0]))  # s holds the genome position for each line

    for file in files:
        vcf_calls = analyzeVcf(config['unzip_dir'] + file)
        bed_calls = analyzeBed(config['unzip_dir'] + file)
        bed_index = [0]
        for lineno in range(len(d)):
            d[lineno] += ','
            if s[lineno] in vcf_calls:
                d[lineno] += vcf_calls[s[lineno]]
            d[lineno] += makeCall(s[lineno], bed_index, bed_calls)

        for line in d:
            print (line)

# routines - Iain 


# Returns a dict of position -> mutation mappings
# Modified from Harald's analyzeVCF, this version returns every mutation with
# its derived value, regardless of whether it was ancestral or not
def readHg19Vcf(file):

    with open(os.path.splitext(file)[0] + '.vcf') as vcffile:
        trace (30, "   Extracting VCF: %s" % vcffile)
        result = {}
        for line in vcffile:
            fields = line.split()
            if (fields[0] == 'chrY' and int(fields[1]) > 0 and fields[3] != '.'
                    and fields[4] != '.'):
                result[fields[1]] = [int(fields[1]), str(fields[3]), str(fields[4])]
        return result


# get number of lines in a file
# probably will fail on utf-8 encoding or binary files in general
def file_len(fname):
    #File length, thanks to StackOverflow
    #https://stackoverflow.com/questions/845058/how-to-get-line-count-cheaply-in-python
    i=-1
    with open(fname) as f:
        for i, l in enumerate(f):
            pass
    return i + 1


# populate agebed table from age.bed
# This procedure dumps what may be in the agebed table and replaces it with the
# ranges defined in age.bed
def populate_age(dbo):
    with open('age.bed') as bedfile:
        cf = csv.reader(bedfile, delimiter=' ')
        ranges = []
        for row in cf:
            try:
                ranges.append((row[0], row[1], row[2]))
            except:
                trace(0,'failed on row of age.bed:{}'.format(row))
        dbo.dc.execute('delete from agebed')
        dbo.dc.execute('drop table if exists tmpt')
        dbo.dc.execute('create temporary table tmpt(a,b,c)')
        dbo.dc.executemany('insert into tmpt values(?,?,?)', ranges)
        dbo.dc.execute('''insert or ignore into bedranges(minaddr,maxaddr)
                           select b,c from tmpt''')
        dbo.dc.execute('''insert into agebed(bID)
                           select id from bedranges
                           inner join tmpt t on t.b=minaddr and t.c=maxaddr''')
        dbo.dc.execute('drop table tmpt')


# populate a table of STR definitions
# Ordering is optional. If not given, table stores SNP names in FTDNA Y111 order.
# Otherwise, It's a 111-number vector.
def populate_STRs(dbo, ordering=None):
    strdefs = (
        'DYS393', 'DYS390', 'DYS19', 'DYS391', 'DYS385a', 'DYS385b',
        'DYS426', 'DYS388', 'DYS439', 'DYS389i', 'DYS392', 'DYS389ii',
        'DYS458', 'DYS459a', 'DYS459b', 'DYS455', 'DYS454', 'DYS447',
        'DYS437', 'DYS448', 'DYS449', 'DYS464a', 'DYS464b', 'DYS464c',
        'DYS464d', 'DYS460', 'YH4', 'YCAIIa', 'YCAIIb', 'DYS456', 'DYS607',
        'DYS576', 'DYS570', 'CDYa', 'CDYb', 'DYS442', 'DYS438', 'DYS531',
        'DYS578', 'DYF395S1a', 'DYF395S1b', 'DYS590', 'DYS537', 'DYS641',
        'DYS472', 'DYF406S1', 'DYS511', 'DYS425', 'DYS413a', 'DYS413b',
        'DYS557', 'DYS594', 'DYS436', 'DYS490', 'DYS534', 'DYS450',
        'DYS444', 'DYS481', 'DYS520', 'DYS446', 'DYS617', 'DYS568',
        'DYS487', 'DYS572', 'DYS640', 'DYS492', 'DYS565', 'DYS710',
        'DYS485', 'DYS632', 'DYS495', 'DYS540', 'DYS714', 'DYS716',
        'DYS717', 'DYS505', 'DYS556', 'DYS549', 'DYS589', 'DYS522',
        'DYS494', 'DYS533', 'DYS636', 'DYS575', 'DYS638', 'DYS462',
        'DYS452', 'DYS445', 'YA10', 'DYS463', 'DYS441', 'Y1B07', 'DYS525',
        'DYS712', 'DYS593', 'DYS650', 'DYS532', 'DYS715', 'DYS504',
        'DYS513', 'DYS561', 'DYS552', 'DYS726', 'DYS635', 'DYS587',
        'DYS643', 'DYS497', 'DYS510', 'DYS434', 'DYS461', 'DYS435')
    if ordering and (len(ordering)==len(strdefs)):
        for tup in zip(ordering,strdefs):
            dbo.dc.execute('insert into strs(ordering,strname) values(?,?)', tup)
    else:
        for tup in enumerate(strdefs):
            dbo.dc.execute('insert into strs(ordering,strname) values(?,?)', tup)


# pull information about the kits from the web api
# if API==None, read from
def get_kits (API='http://haplogroup-r.org/api/v1/uploads.php', qry='format=json'):
    import requests, json
    try:
        # choose where to pull the kit data
        if not API:
            trace(0, 'reading kit info from json.out')
            js = json.loads(open('json.out').read())
        else:
            trace(0, 'reading kit info from the web')
            url = '?'.join([API, qry])
            res = requests.get(url)
            js = json.loads(res.content)
            open('json.out','w').write(json.dumps(js))
    except:
        print('Failed to pull kit metadata from {}'.format(API))
        raise # fixme - what to do on error
        
    return js

# update the information about the kits
# the input is js, a json object that comes from the Haplogroup-R DW API
def update_metadata(db, js):
    blds = {'b38': 'hg38', 'b19': 'hg19', 'b37': 'hg19'}
    rows = [(
        # fields that go into dataset table directly
        jr['kitId'].strip(), jr['uploaded'], jr['dataFile'], jr['long'],
        jr['lat'], jr['otherInfo'], jr['origFileName'], jr['birthYear'],
        jr['approxHg'],
        # need inserting into their own tables
        jr['country'], jr['normalOrig'], jr['lab'], blds[jr['build']],
        jr['surname'], jr['testType'], jr['isNGS'])
        for jr in js
        ]
    trace(0, 'first row out of {}:{}'.format(len(rows),rows[0]))
    trace(0, '{} unique kit ids'.format(len(set([v['kitId'] for v in js]))))
    trace(0, '{} null surname'.format(len([v['surname'] for v in js if not v['surname']])))

    # populate the dependency tables
    # (testtype,isNGS) goes into testtypes
    tups = [y for y in set([(r[-2],r[-1]) for r in rows])]
    db.dc.executemany('insert into testtype(testNm,isNGS) values(?,?)', tups)

    # (surname+kitId+build) goes into person
    # fixme: we need a DNA-to-person mapping. This is a big kludge
    tups = [y for y in set([(r[-3],r[0],r[-4]) for r in rows])]
    db.dc.executemany('insert into person(surname,firstname,middlename) values(?,?,?)',
                          tups)

    for tbl,val,idx in (('country','country',-7),
                        ('surname', 'surname',-3),
                        ('origin', 'origin',-6),
                        ('lab', 'labNm',-5),
                        ('build', 'buildNm',-4)):
        tups = [(y,) for y in set([v[idx] for v in rows])]
        trace(1, 'first tuple to insert into {}: {}'.format(tbl, tups[0]))
        db.dc.executemany('insert or ignore into {}({}) values(?)'.format(tbl,val),
                              tups)

    # create temporary table, where columns correspond to values above
    db.dc.execute('''create temporary table tmpt(
           a TEXT, b TEXT, c TEXT, d TEXT,
           e TEXT, f TEXT, g TEXT, h TEXT,
           i TEXT,
           j TEXT, k TEXT, l TEXT, m TEXT,
           n TEXT, o TEXT, p TEXT)''')
    db.dc.executemany('''INSERT INTO tmpt(a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', rows)
    db.dc.execute('''
        INSERT INTO dataset(kitId, importDt, fileNm, lng,
            lat, otherInfo, origFileNm, birthYr,
            approxHg,
            countryID, normalOrigID, labID, buildID, testTypeID, DNAID, surnameID)
        SELECT a, b, c, d,
            e, f, g, h,
            i,
            cn.id, oc.id, ln.id, bn.id, tt.id, pn.id, sn.id
        FROM tmpt
        INNER JOIN country cn ON
            tmpt.j = cn.country or (cn.country is NULL and tmpt.j is NULL)
        INNER JOIN origin oc ON
            tmpt.k = oc.origin or (oc.origin is NULL and tmpt.k is NULL)
        INNER JOIN lab ln ON tmpt.l = ln.labNm
        INNER JOIN build bn ON tmpt.m = bn.buildNm
        INNER JOIN surname sn ON
            tmpt.n = sn.surname or (sn.surname is NULL and tmpt.n is NULL)
        INNER JOIN person pn ON
            (tmpt.n = pn.surname or (tmpt.n is NULL and pn.surname is NULL)) AND
            (tmpt.a = pn.firstname or (tmpt.a is NULL and pn.firstname is NULL)) AND
            (tmpt.m = pn.middlename or (tmpt.m is NULL and pn.middlename is NULL))
        INNER JOIN testtype tt ON tmpt.o = tt.testNm and tmpt.p = tt.isNGS''')
    trace(1, '{} rows inserted into dataset'.format(db.dc.execute('select count(*) from dataset').fetchone()[0]))
    db.dc.execute('drop table tmpt')

# load data into the contig table
def populate_contigs(db):
    bid = db.get_build_byname('hg19')
    db.dc.execute('insert into Contig(buildID,description,length) values(?,?,?)',
                      (bid, 'chrY', 59373566))
    bid = db.get_build_byname('hg38')
    db.dc.execute('insert into Contig(buildID,description,length) values(?,?,?)',
                      (bid, 'chrY', 57227415))

# populate dataset information from Haplogroup-R data warehouse API
def populate_fileinfo(dbo, fromweb=True):
    if fromweb:
        js = get_kits()
    else:
        js = get_kits(API=None)
    update_metadata(dbo, js)

# update snp definitions from a csv DictReader instance
# fixme - update snpnames
def updatesnps(db, snp_reference, buildname='hg38'):
    bid = db.get_build_byname(buildname)
    db.dc.execute('create temporary table tmpt(a integer, b integer, c text, d text, e text, unique(a,b,c,d,e))')
    db.dc.executemany('INSERT OR IGNORE INTO tmpt(a,b,c,d,e) VALUES (?,?,?,?,?)',
             ((bid, rec['start'],
                   rec['allele_anc'].strip(), rec['allele_der'].strip(), rec['Name'])
                     for rec in snp_reference))
    db.dc.execute('''insert or ignore into alleles(allele) 
                        select distinct c from tmpt''')
    db.dc.execute('''insert or ignore into alleles(allele) 
                        select distinct d from tmpt''')
    db.dc.execute('''insert or ignore into variants(buildID, pos, anc, der)
                        select a, b, an.id, dr.id from tmpt
                        inner join alleles an on an.allele = c
                        inner join alleles dr on dr.allele = d''')
    db.dc.execute('''insert or ignore into snpnames(snpname,vID)
                        select t.e, v.id from tmpt t, variants v, alleles a, alleles d
                        where t.c=a.allele and v.anc=a.id and
                              t.d=d.allele and v.der=d.id and
                              v.pos = t.b and v.buildID=t.a''')

    db.dc.execute('drop table tmpt')

# pull SNP definitions from the web at ybrowse.org
# this should be called after the build table is populated
# refresh files if they are older than maxage; do nothing if maxage < 0
def get_SNPdefs_fromweb(db, maxage, url='http://ybrowse.org/gbrowse2/gff'):
    import urllib, time
    if maxage < 0:
        return
    for (build,) in db.dc.execute('select buildNm from build'):
        deltat = maxage + 1
        fbase = 'snps_{}.csv'.format(build)
        trace (0, 'refresh: {}'.format(fbase))
        fget = os.path.join(url, fbase)
        fname = os.path.join(config['REDUX_DATA'], fbase)
        try:
            if os.path.exists(fname):
                deltat = time.time() - os.path.getmtime(fname)
            if deltat > maxage:
                urllib.request.urlretrieve(fget, fname)
                deltat = time.time() - os.path.getmtime(fname)
        except:
            pass
        if not os.path.exists(fname) or deltat > maxage:
            trace(0, 'failed to update {} from the web'.format(fname))
    return

# populate SNP definitions; refresh from web if we have is older than maxage (seconds)
def populate_SNPs(dbo, maxage=3600*24*5):
    get_SNPdefs_fromweb(dbo, maxage=maxage)
    # update known snps for hg19 and hg38
    with open(os.path.join(config['REDUX_DATA'], config['b37_snp_file'])) as snpfile:
        snp_reference = csv.DictReader(snpfile)
        updatesnps(db, snp_reference, 'hg19')
    with open(os.path.join(config['REDUX_DATA'], config['b38_snp_file'])) as snpfile:
        snp_reference = csv.DictReader(snpfile)
        updatesnps(db, snp_reference, 'hg38')

# populate calls, quality, and variants from a VCF file
def populate_from_VCF_file(bid, pid, fname):
    # stub work in progress Jef
    return

# test framework
if __name__ == '__main__':
    # print (config)
    db = DB(drop=True)
    db.create_schema()
    populate_fileinfo(db, fromweb=True)
    populate_STRs(db)
    populate_SNPs(db)
    populate_contigs(db)
    populate_age(db)
    db.commit()
    db.close()

sanity_tests='''
./lib.py
should produce no errors and produce variants.db after some time

sqlite3 variants.db
sqlite> .mode tabs
sqlite> .header on

sqlite> select vid, snpname, der, allele from snpnames inner join variants v on v.id=vid and v.pos=6753258 inner join alleles a on v.der=a.id;

should return nine rows similar to
vID	snpname	der	allele
7574	L147.2	3	C
7574	L147.5	3	C
7574	L147.3	3	C
179549	L1283	4	G
181076	Y8884	2	A
7574	L147.4	3	C
7574	PF4883	3	C
7574	L147.1	3	C
7574	L147	3	C

sqlite> select count(*) from variants;
613049
'''