# authors/licensing{{{

# @author: Iain McDonald
# Contributors: Jef Treece, Harald Alvestrand, Zak Jones
# Purpose: Reduction and comparison script for Y-chromosome NGS test data
# For free distribution under the terms of the GNU General Public License,
# version 3 (29 June 2007)
# https://www.gnu.org/licenses/gpl.html

# }}}
# libs {{{

import sys,os,sqlite3,yaml,time,csv,json,numpy as np

# }}}

REDUX_CONF = os.environ['REDUX_CONF']
config = yaml.load(open(REDUX_CONF))
start_time = 0 # need to fix this

#TODO: need to put this info properly into yaml file (for now, I'm hacking bashrc)
REDUX_ENV = os.environ['REDUX_ENV']
REDUX_SQL = os.environ['REDUX_SQL']
REDUX_DATA = os.environ['REDUX_DATA']

class DB(object):
    
    def __init__(self, dbfname='variant.db'):
        self.dbfname = dbfname
        self.db = sqlite3.connect(self.dbfname)
        self.dc = self.cursor()

    def cursor(self):
        return self.db.cursor()

    def run_sql_file(self,FILE):
        with open(REDUX_SQL+'/'+FILE,'r') as fh:
            self.dc.executescript(fh.read())

    def commit(self):
        self.db.commit()

    def create_schema(self):
        self.run_sql_file('schema.sql')
        
    # get build identifier by its name; creates new entry if needed
    def get_build_by_name(self, buildname='hg38'):
        dc = self.dc.execute('select id from builds where buildname=?', (buildname,))
        bid, = dc.fetchone()
        if not bid:
            self.dc.execute('insert into builds(buildname) values (?)', (buildname,))
            bid = self.dc.lastrowid
        return bid

    # insert an array of variants
    # fixme - handle dedupe
    def insert_variants(self, variant_array, buildname='hg38'):
        bid = self.get_build_byname(buildname)
        self.dc.executemany('INSERT INTO variants(buildID,pos,ref,alt) VALUES (?,?,?,?)', [(bid,)+v for v in variant_array])

    # insert a vector of variant ids to insert for a given person specified by pid
    def insert_calls(self, pid, calls):
        self.dc.executemany('INSERT INTO vcfcalls(pID,vID) values (?,?)', [(pid,v) for v in calls])

    # update snp definitions from a csv DictReader instance
    # fixme - update snpnames
    def updatesnps(self,snp_reference, buildname='hg38'):
        bid = self.get_build_byname(buildname)
        self.dc.executemany('INSERT INTO variants(buildID,pos,ref,alt) VALUES (?,?,?,?)',
            ((bid, rec['start'], rec['allele_anc'], rec['allele_der']) for rec in snp_reference))

    # fixme: migrate to schema
    def insert_sample_sort_data(self):

        #sample data: 3019783,M343,1,1,Null,1,1,1,1,1,1,1
        #{'v': '3019783', 'n': 'M343', 'k1': '1', 'k2': '1', 'k3': 'Null', 'k4': '1', 'k5': '1', 'k6': '1', 'k7': '1', 'k8': '1', 'k9': '1', 'k10': '1', 'k11': None, 'k12': None}

        #create table s_kits(
        # kit_id  int,  -- later this can be person_id
        # sort_order int
        #);

        #create table s_variants (
        # -- variant_id int, -- not needed for prototype
        # variant_loc int,  -- PK
        # name varchar(20)
        # -- old_reference varchar(2), -- commenting out right now cuz not part of ian's doc
        #);

        #create table s_calls(
        # kit_id int,
        # variant_loc int,
        # assigned boolean
        #);

        cols=10
        for k in range(1,cols+1):
            self.dc.execute("insert into datasets (kitname) values ("+str(k)+");")

        # fixme - kitid != kitname
        with open(REDUX_DATA+'/sample-sort-data.csv','r') as FILE:
            for row in csv.DictReader(FILE,'v n k1 k2 k3 k4 k5 k6 k7 k8 k9 k10'.split()):
                row = json.loads(json.dumps(row).replace('\\ufeff','')) #hack: remove byte order mark
                # fixme - duplicate locations
                self.dc.execute("insert into variants (variant_loc,name) values ("+row['v']+",'"+row['n']+"');")
                #print(' - inserting sample variant data: '+str(row['v']))
                for k in range(1,cols+1):
                    kv = str(row['k'+str(k)])
                    #'null' if kv == "None" else kv
                    vv = str(row['v'])
                    #print (kv)
                    # fixme assigned, get proper person ID, variant ID
                    self.dc.execute("insert into vcfcalls (pID,vID) values ("+str(k)+","+vv+","+kv+");")
                    #self.commit()
                    #print (kv+":"+vv)
                #break;
                #sys.exit()
                #print(row)
                #print(row.encode('utf-8-sig'))
            #for (l,n,v1,v2,v3,v4,v5,v6,v7,v8,v9,v10,v11,v12) in dr]
            #    print (n)
            #self.dc.executemany("insert into kits (col1, col2) VALUES (?, ?);", to_db)
            #(variant_loc,name,) = t_db
            #con.commit()
            #con.close()
        self.commit()
        
    # fixme - migrate to schema
    def sort_data(self):

        print("===")
        print("FILTER, step: A ")
        print("===")
        sql = "select distinct variant_loc from vcfcalls;"
        self.dc.execute(sql)
        A = self.dc.fetchall()
        print("A - distinct variants")
        print(A) #A - distinct variants
        print("---")
        print('numA - num distinct variants')
        print(len(A)) #numA - num distinct variants

        print("===")
        print("FILTER - step: B")
        print("===")
        sql = "select distinct variant_loc from vcfcalls where assigned = 0;"
        self.dc.execute(sql)
        B1 = self.dc.fetchall()
        B0 = list(set(A)-set(B1))
        print("B0 - variants that don't have negs")
        print(B0) #B0 - variants that don't have negs
        print("---")
        print("B1 - variants that have negs")
        print(B1) #B1 - variants that have negs 

        print("===")
        print("FILTER - step: C")
        print("===")
        sql = "select variant_loc,count(*) as cnt from vcfcalls where assigned = 1 group by variant_loc;"
        self.dc.execute(sql)
        F = self.dc.fetchall()
        Fa = list(filter(lambda x: x[1]==(len(A)-1), F))
        Fb = [(a) for a,b in Fa] #strip out 2nd element, the count
        C1 = list(set(B1) & set(Fb)) #intersection
        C0 = list(set(B1)-set(C1))
        print("list of *all* one person +ve's")
        print(Fa)
        print("---")
        print("not singletons")
        print(C0) #C0 - not singletons
        print("---")
        print("singletons") #C1 - singletons
        print(C1)

        print("===")
        print("FILTER - step: D")
        print("===")
        sql = "select distinct variant_loc from vcfcalls where assigned is null group by variant_loc;"
        self.dc.execute(sql)
        F = self.dc.fetchall()
        D0 = list(set(C1)-set(F))
        D1 = list(set(F)-set(D0))
        print("list of variants that are sometimes not called")
        print(F)
        print("---")
        print("imperfect variants")
        print(D0) #D0 - imperfect variants
        print("---")
        print("calls of perfect share variants - these go through the next PROCESS, SORT")
        print(D1) #D1 - perfect share variants

        #NOTE: a type study {{{
        #------------------------------

        #I'm thinking byK is what we're looking to work with

        #byV = [
        #    { v1:
        #        ({pos:[k4,k3]},{cnt:2},{neg:[]},{unk:[]})
        #        },
        #    { v2:
        #        ({pos:[k1,k2,k3]},{cnt:3},{neg:[]},{unk:[]})
        #        },
        #    { v3:
        #        ({pos:[k4,k3]},{cnt:2},{neg:[]},{unk:[]})
        #        },
        #    { v4:
        #        ({pos:[k2,k1]},(cnt:2},{neg:[]},{unk:[]})
        #        }
        #    ]

        #byK = [
        #    { k1:
        #        ({pos:[v2,v4]},{cnt:2},{neg:[]},{unk:[]})
        #        },
        #    { k2:
        #        ({pos,[v2,v4]},{cnt:2},{neg:[]},{unk:[]})
        #        },
        #    { k3:
        #        ({pos,[v1,v2,v3]},{cnt:2},{neg:[]},{unk:[]})
        #        },
        #    { k4:
        #        ({pos,[v1,v3]},{cnt:2},{neg:[]},{unk:[]})
        #        }
        #    ]
            
        #------------------------------ }}}

        print("===")
        print("SORT")
        print("===")
        sql = "select kit_id,variant_loc from vcfcalls order by kit_id, variant_loc;"
        self.dc.execute(sql)
        F = self.dc.fetchall()
        print("all kits + variants")
        print("+ grabbing kits by variant: 3019783")
        #[(1, 3019783), (1, 6920349), (1, 7378685), (1, 8928037), ... ]
        Fa = list(filter(lambda x: x[1]==3019783, F))
        Fb = [(a) for a,b in Fa] #strip out 2nd element, the count
        #[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        print(Fb)
        print("---")
        
        sys.exit()

        #sql_2b = "select variant_loc,count(*) as pos_v_cnt from calls where assigned = 0 group by variant_loc order by count(*) desc;"
        #self.dc.execute(sql_2b)
        #varAn = self.dc.fetchall()
        #print("---")
        #print("variant negative check")
        #print(varAn)

        sql_2b = "select variant_loc,count(*) as pos_v_cnt from vcfcalls where assigned = 0 group by variant_loc order by count(*) desc;"
        sql_2c = "select variant_loc,count(*) as pos_v_cnt from vcfcalls where assigned is not null group by variant_loc order by count(*) desc;"
        self.dc.execute(sql_2c)
        varAa = self.dc.fetchall()
        print("---")
        print("variant all check")
        print(varAa)
        #(3) 9 perfectly called variants - execute sort on these
        #(4) 6 imperfectly called variants - do Step A

        sql_3 = "select * from vcfcalls order by kit_id,assigned;"
        self.dc.execute(sql_3)
        callsA = self.dc.fetchall()
        print("---")
        #[(1, 12060401, None), (1, 6920349, 0), (1, 7378685, 0), (1, 13668461, 0), (1, 19538924, 0), ... ]
        print (callsA);

        #Note: build the default structure with the kits ordered like kitA and the variants ordered like varA
        #[{"k1":[{"v12060401",1)},{"v6920349",1), ... ]}
        #[{"k2":[{"v12060401",1)},{"v6920349",None), ... ]}
        #and display it
        #for call in calls:
        #   for K in kits:
        #    ...
        #   sort_positive_variants(kit_id)

    # populate a table of STR definitions
    def populate_STRs(self, ordering=None):
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
                self.dc.execute('insert into str(ordering,strname) values(?,?)', tup)
        else:
            for tup in enumerate(strdefs):
                self.dc.execute('insert into str(ordering,strname) values(?,?)', tup)














































































































