# SEAL db - Simple, Efficient And Lite database for NGS

## Installation

First of all clone the repo :
```bash
git clone https://github.com/mobidic/seal.git
```

### Install dependencies

#### Conda

Please install conda ([documentation here](https://docs.conda.io/projects/conda/en/latest/user-guide/install/index.html))

`conda env create -f environment.yml`

### Execution

This is an example of a typical execution of this Flask application on :
- __Operating System__: Debian GNU/Linux 10 (buster)
- __Kernel__: Linux 4.19.0-17-amd64
- __Architecture__: x86-64

It can be slightly different depending on your Operating System, Kernel, Architecture, Environment...

#### Step by step

- Activate your virtual environment :
```bash
conda activate seal
````
- Install VEP
  - Follow [VEP installation guide](https://www.ensembl.org/info/docs/tools/vep/script/vep_download.html#installer)
  - Download all packages needed :
    - dbNSFP
    - MaxEntScan
    - SpliceAI
    - dbscSNV
    - GnomAD
  - Please edit file : `seal/static/vep.config.json` 
    - {dir_vep}
    - {dir_vep_plugins}
    - {GnomAD_vcf}
    - {fasta}
- Export the environment variables
```bash
export FLASK_APP=seal
export FLASK_ENV=development
export PYTHONPATH=${PWD}
```
- Start database server
```bash
initdb -D ${PWD}/seal/seal.db
pg_ctl -D ${PWD}/seal/seal.db -l ${PWD}/seal/seal.db.log start
```
- Issue [#26](https://github.com/mobidic/SEAL/issues/26)
  - comment line on `seal/__init__.py`
  ```python
  # from seal import routes
  # from seal import schedulers
  # from seal import admin
  ```
- Initialize database
```bash
python insertdb.py
flask db init
flask db migrate -m "Init DataBase"
```
  - __[Optional]__ Add Gene as Region (usefull to create _in-silico_ panels)
  ```bash
  wget -qO- http://hgdownload.cse.ucsc.edu/goldenpath/hg19/database/ncbiRefSeq.txt.gz   | gunzip -c - | awk -v OFS="\t" '{ if (!match($13, /.*-[0-9]+/)) { print $3, $5-2000, $6+2000, $13; } }' -  | sort -u > ncbiRefSeq.hg19.sorted.bed
  python insert_genes.py
  ```
  - __[Optional]__ Add OMIM (for transmission and relative diseases) __/!\ YOU NEED AN OMIM ACCESS TO DOWNLOAD FILE__
  ```bash
  wget -qO- https://data.omim.org/downloads/{{YOUR API KEY}}/genemap2.txt
  python insert_OMIM.py
  ```
- Issue [#26](https://github.com/mobidic/SEAL/issues/26)
  - uncomment line on `seal/__init__.py`
  ```python
  from seal import routes
  from seal import schedulers
  from seal import admin
  ```
- Launch the flask app
```bash
flask run
```

### Miscellaneous

- Update database
```bash
flask db migrate -m "message"
flask db upgrade
```
- Enable/disable maintenance mode
```bash
# Enable
export SEAL_MAINTENANCE="TRUE"  # possibilities : "true", "t", "1", "on" (case insensitive)
# Disable
export SEAL_MAINTENANCE="FALSE" # possibilities : "false", "f", "0", "off" (case insensitive)
# unset SEAL_MAINTENANCE # disable Maintenance mode too
```
- Start/Stop the datatabase server
```bash
pg_ctl -D ${PWD}/seal/seal.db -l ${PWD}/seal/seal.db.log start
pg_ctl -D ${PWD}/seal/seal.db -l ${PWD}/seal/seal.db.log stop
```

#### All commands

```bash
conda activate seal
export FLASK_APP=seal
export FLASK_DEBUG=on
export PYTHONPATH=${PWD}
initdb -D ${PWD}/seal/seal.db
pg_ctl -D ${PWD}/seal/seal.db -l ${PWD}/seal/seal.db.log start
# python insertdb.py
# flask db init
# flask db migrate -m "Init DataBase"
flask run
# flask db migrate -m "message"
# flask db upgrade
# pg_ctl -D ${PWD}/seal/seal.db -l ${PWD}/seal/seal.db.log stop
```
