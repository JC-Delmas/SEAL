import json
import numpy
import shlex
import random
import datetime
import subprocess

from pathlib import Path
from sqlalchemy.orm.exc import NoResultFound

from anacore import annotVcf

from seal import app, scheduler, db
from seal.models import Sample, Variant, Family, Var2Sample, Run, Transcript, Team


CONSEQUENCES_DICT = {
    "stop_gained": 20,
    "stop_lost": 20,
    "splice_acceptor_variant": 10,
    "splice_donor_variant": 10,
    "frameshift_variant": 10,
    "transcript_ablation": 10,
    "start_lost": 10,
    "transcript_amplification": 10,
    "missense_variant": 10,
    "protein_altering_variant": 10,
    "splice_region_variant": 10,
    "inframe_insertion": 10,
    "inframe_deletion": 10,
    "incomplete_terminal_codon_variant": 10,
    "stop_retained_variant": 10,
    "start_retained_variant": 10,
    "synonymous_variant": 10,
    "coding_sequence_variant": 10,
    "mature_miRNA_variant": 10,
    "intron_variant": 10,
    "NMD_transcript_variant": 10,
    "non_coding_transcript_exon_variant": 5,
    "non_coding_transcript_variant": 5,
    "3_prime_UTR_variant": 2,
    "5_prime_UTR_variant": 2,
    "upstream_gene_variant": 0,
    "downstream_gene_variant": 0,
    "TFBS_ablation": 0,
    "TFBS_amplification": 0,
    "TF_binding_site_variant": 0,
    "regulatory_region_ablation": 0,
    "regulatory_region_amplification": 0,
    "regulatory_region_variant": 0,
    "feature_elongation": 0,
    "feature_truncation": 0,
    "intergenic_variant": 0
}
GNOMADG = [
    "gnomADg_AF_AFR",
    "gnomADg_AF_AMR",
    "gnomADg_AF_ASJ",
    "gnomADg_AF_EAS",
    "gnomADg_AF_FIN",
    "gnomADg_AF_NFE",
    "gnomADg_AF_OTH"
]
ANNOT_TO_SPLIT = [
    "Existing_variation",
    "Consequence",
    "CLIN_SIG",
    "SOMATIC",
    "PHENO",
    "PUBMED",
    "TRANSCRIPTION_FACTORS",
    "VAR_SYNONYMS",
    "DOMAINS",
    "FLAGS"
]
MISSENSES = [
    "CADD_raw_rankscore_hg19",
    "VEST4_rankscore",
    "MetaSVM_rankscore",
    "MetaLR_rankscore",
    "Eigen-raw_coding_rankscore",
    "Eigen-PC-raw_coding_rankscore",
    "REVEL_rankscore",
    "BayesDel_addAF_rankscore",
    "BayesDel_noAF_rankscore",
    "ClinPred_rankscore"
]
SPLICEAI = [
    "SpliceAI_pred_DS_AG",
    "SpliceAI_pred_DS_AL",
    "SpliceAI_pred_DS_DG",
    "SpliceAI_pred_DS_DL"
]


def get_token(path_tokens):
    for file in path_tokens.iterdir():
        if file.suffix == '.token':
            return file
    return False


def random_color(format="HEX"):
    red = random.randint(0, 255)
    green = random.randint(0, 255)
    blue = random.randint(0, 255)
    if format == "HEX":
        return f'#{red:02X}{green:02X}{blue:02X}'
    if format == "RGB":
        return f'({red},{green},{blue})'


# cron examples
@scheduler.task('cron', id='import vcf', second="*/20")
def importvcf():
    # Load config file

    vep_config_file = Path(app.root_path).joinpath('static/vep.config.json')
    with open(vep_config_file, "r") as tf:
        vep_config = json.load(tf)

    # Check launchable
    path_inout = Path(app.root_path).joinpath('static/temp/vcf/')
    current_token = get_token(path_inout)
    path_locker = path_inout.joinpath('.lock')

    if current_token and not path_locker.exists():
        app.logger.info("---------------- Create A New Sample ----------------")

        # Create lock file
        lockFile = open(path_locker, 'x')
        lockFile.close()

        # Change token to treat file
        current_file = current_token.with_suffix('.treat')
        current_token.rename(current_file)

        # Load data
        with current_file.open('r') as json_sample:
            data = json.load(json_sample)

        # Come from interface
        try:
            interface = data["interface"]
        except KeyError:
            interface = False

        # Sample Creation
        try:
            sample = data["sample"]
            sample_name = sample["name"]
            vcf_path = Path(data["vcf_path"])
            if not vcf_path.exists():
                app.logger.error(f'Path does not exist for : {vcf_path}')
                return
        except KeyError as e:
            error_file = current_file.with_suffix('.error')
            current_file.rename(error_file)
            app.logger.error(e)
            return

        try:
            affected = sample["affected"]
            if not isinstance(sample["affected"], (int, bool)):
                raise TypeError
        except (KeyError, TypeError):
            app.logger.debug('Affected status is unclear.')
            affected = False

        try:
            index = sample["index"]
            if not isinstance(sample["index"], (int, bool)):
                raise TypeError
        except (KeyError, TypeError):
            app.logger.debug('Index case status is unclear.')
            index = False

        sample = Sample(samplename=sample_name, affected=affected, index=index)
        db.session.add(sample)
        db.session.commit()
        app.logger.info(f'Sample {sample} added to SEAL !')

        # Family processing
        try:
            family_name = data["family"]["name"]
            family = Family.query.filter_by(family=family_name).one()
        except KeyError:
            family = False
            app.logger.debug(f'No family associated with : {sample}.')
        except NoResultFound:
            if family_name:
                app.logger.debug(f'Family {family_name} not found !')
                family = Family(family=family_name)
                db.session.add(family)
                db.session.commit()
                app.logger.info(f'{family} added to SEAL !')
            else:
                family = False
        finally:
            if family:
                sample.familyid = family.id
                db.session.commit()
                app.logger.info(f'Family {family} asssociated to {sample} !')

        # Run processing
        try:
            run_name = data["run"]["name"]
            run = Run.query.filter_by(name=run_name).one()
        except KeyError:
            run = False
            app.logger.debug(f'No run associated with : {sample}.')
        except NoResultFound:
            if run_name:
                app.logger.debug(f'Run "{run_name}" not found !')
                try:
                    run_alias = data["run"]["alias"]
                except KeyError:
                    run_alias = None
                run = Run(name=run_name, alias=run_alias)
                db.session.add(run)
                db.session.commit()
                app.logger.debug(f'{run} added to SEAL !')
            else:
                run = False
        finally:
            if run:
                sample.runid = run.id
                db.session.commit()
                app.logger.info(f'{run} asssociated to {sample} !')

        # Team(s) processing
        try:
            if not isinstance(data["teams"], list):
                raise TypeError
            teams = data["teams"]
        except (KeyError, TypeError):
            app.logger.debug(f'No teams associated with : {sample}.')
            teams = list()

        for team in teams:
            try:
                team_name = team["name"]
                team_db = Team.query.filter_by(teamname=team_name).one()
                sample.teams.append(team_db)
                db.session.commit()
            except KeyError:
                team_db = False
                app.logger.warn(f'Keyword "name" missing in {team} (team). Skipping...')
            except NoResultFound:
                if team_name:
                    app.logger.debug(f'Team "{team_name}" not found !')
                    try:
                        team_color = team["color"]
                        if not team_color:
                            raise ValueError
                    except (ValueError, KeyError):
                        team_color = random_color()
                    team_db = Team(teamname=team_name, color=team_color)
                    db.session.add(team)
                    db.session.commit()
                    app.logger.debug(f'{team} added to SEAL !')
            finally:
                if team:
                    sample.teams.append(team_db)
                    db.session.commit()
                    app.logger.info(f'{team_db} asssociated to {sample} !')

        current_date = datetime.datetime.now().isoformat()

        vcf_vep = path_inout.joinpath(f'{vcf_path.stem}.vep.vcf')
        stats_vep = path_inout.joinpath(f'{vcf_path.stem}.vep.html')
        vep_cmd = "vep " + \
            f" --input_file {vcf_path} " + \
            f" --output_file {vcf_vep} " + \
            f" --stats_file {stats_vep} " + \
            f" --dir {vep_config['dir']} " + \
            f" --plugin dbNSFP,{vep_config['dbNSFP']},BayesDel_addAF_rankscore,BayesDel_noAF_rankscore,CADD_raw_rankscore,CADD_raw_rankscore_hg19,ClinPred_rankscore,DANN_rankscore,DEOGEN2_rankscore,Eigen-PC-raw_coding_rankscore,Eigen-raw_coding_rankscore,FATHMM_converted_rankscore,GERP++_RS_rankscore,GM12878_fitCons_rankscore,GenoCanyon_rankscore,H1-hESC_fitCons_rankscore,HUVEC_fitCons_rankscore,LINSIGHT_rankscore,LIST-S2_rankscore,LRT_converted_rankscore,M-CAP_rankscore,MPC_rankscore,MVP_rankscore,MetaLR_rankscore,MetaSVM_rankscore,MutPred_rankscore,MutationAssessor_rankscore,MutationTaster_converted_rankscore,PROVEAN_converted_rankscore,Polyphen2_HDIV_rankscore,Polyphen2_HVAR_rankscore,PrimateAI_rankscore,REVEL_rankscore,SIFT4G_converted_rankscore,SIFT_converted_rankscore,SiPhy_29way_logOdds_rankscore,VEST4_rankscore,bStatistic_converted_rankscore,fathmm-MKL_coding_rankscore,fathmm-XF_coding_rankscore,integrated_fitCons_rankscore,phastCons100way_vertebrate_rankscore,phastCons17way_primate_rankscore,phastCons30way_mammalian_rankscore,phyloP100way_vertebrate_rankscore,phyloP17way_primate_rankscore,phyloP30way_mammalian_rankscore " + \
            f" --plugin  MaxEntScan,{vep_config['MaxEntScan']} " + \
            f" --plugin SpliceAI,snv={vep_config['SpliceAI_snv']},indel={vep_config['SpliceAI_indel']} " + \
            f" --plugin dbscSNV,{vep_config['dbscSNV']} " + \
            f" --custom {vep_config['gnomADg']},gnomADg,vcf,exact,0,AF_AFR,AF_AMR,AF_ASJ,AF_EAS,AF_FIN,AF_NFE,AF_OTH,AF " + \
            f" --fasta {vep_config['fasta']} " + \
            f" --fork {vep_config['fork']} " + \
            " --species homo_sapiens " + \
            " --assembly GRCh37 " + \
            " --cache " + \
            " --offline " + \
            " --merged " + \
            " --buffer_size 5000 " + \
            " --vcf " + \
            " --variant_class " + \
            " --sift b " + \
            " --polyphen b " + \
            " --nearest transcript " + \
            " --distance 5000,5000 " + \
            " --overlaps " + \
            " --gene_phenotype " + \
            " --regulatory " + \
            " --show_ref_allele " + \
            " --total_length " + \
            " --numbers " + \
            " --vcf_info_field ANN " + \
            " --terms SO " + \
            " --shift_3prime 0 " + \
            " --shift_genomic 1 " + \
            " --hgvs " + \
            " --hgvsg " + \
            " --shift_hgvs 1 " + \
            " --transcript_version " + \
            " --protein " + \
            " --symbol " + \
            " --ccds " + \
            " --uniprot " + \
            " --tsl " + \
            " --appris " + \
            " --canonical " + \
            " --biotype " + \
            " --domains " + \
            " --xref_refseq " + \
            " --check_existing " + \
            " --clin_sig_allele 1 " + \
            " --pubmed " + \
            " --var_synonyms " + \
            " --force"

        app.logger.info("------ Variant Annotation with VEP ------")
        args_vep = shlex.split(vep_cmd)
        app.logger.info(args_vep)
        with subprocess.Popen(args_vep, stdout=subprocess.PIPE) as proc:
            app.logger.info(f"------ {proc.stdout.read()}")
        app.logger.info("------ END VEP ------")

        try:
            with annotVcf.AnnotVCFIO(vcf_vep) as vcf_io:
                for v in vcf_io:
                    if v.alt[0] == "*":
                        continue
                    variant = Variant.query.get(f"{v.chrom}-{v.pos}-{v.ref}-{v.alt[0]}")
                    if not variant:
                        annotations = [{
                            "date": current_date,
                            "ANN": list()
                        }]

                        for annot in v.info["ANN"]:
                            # Split annotations
                            for splitAnn in ANNOT_TO_SPLIT:
                                if splitAnn == 'VAR_SYNONYMS':
                                    try:
                                        var_synonyms = dict()
                                        for vs in annot[splitAnn].split("--"):
                                            key, values = vs.split("::")
                                            values_array = values.split("&")
                                            var_synonyms[key] = values_array

                                        annot[splitAnn] = var_synonyms
                                    except AttributeError:
                                        annot[splitAnn] = dict()
                                else:
                                    try:
                                        annot[splitAnn] = annot[splitAnn].split("&")
                                    except AttributeError:
                                        annot[splitAnn] = []

                            # transcript
                            transcript = Transcript.query.get(annot["Feature"])
                            if not transcript and annot["Feature"] is not None:
                                transcript = Transcript(
                                    feature=annot["Feature"],
                                    biotype=annot["BIOTYPE"],
                                    feature_type=annot["Feature_type"],
                                    symbol=annot["SYMBOL"],
                                    symbol_source=annot["SYMBOL_SOURCE"],
                                    gene=annot["Gene"],
                                    source=annot["SOURCE"],
                                    protein=annot["ENSP"],
                                    canonical=annot["CANONICAL"],
                                    hgnc=annot["HGNC_ID"]
                                )
                                db.session.add(transcript)

                            # Get consequence score
                            consequence_score = 0
                            for consequence in annot["Consequence"]:
                                consequence_score += CONSEQUENCES_DICT[consequence]
                            annot["consequenceScore"] = consequence_score

                            # Get Exon/Intron
                            annot["EI"] = None
                            if annot["EXON"] is not None:
                                annot["EI"] = f"Exon {annot['EXON']}"
                            if annot["INTRON"] is not None:
                                annot["EI"] = f"Intron {annot['INTRON']}"

                            # Get Exon/Intron
                            annot["canonical"] = True if annot['CANONICAL'] == 'YES' else False

                            # missense
                            missenses = list()
                            for value in MISSENSES:
                                missenses.append(annot[value])
                            missenses = numpy.array(missenses, dtype=numpy.float64)
                            mean = numpy.nanmean(missenses)
                            annot["missensesMean"] = None if numpy.isnan(mean) else mean

                            # max spliceAI
                            spliceAI = list()
                            for value in SPLICEAI:
                                spliceAI.append(annot[value])
                            spliceAI = numpy.array(spliceAI, dtype=numpy.float64)
                            max = numpy.nanmax(spliceAI)
                            annot["spliceAI"] = None if numpy.isnan(max) else max

                            # max MaxEntScan
                            annot["MES_var"] = None
                            if annot["MaxEntScan_alt"] is not None and annot["MaxEntScan_ref"] is not None:
                                annot["MES_var"] = -100 + (float(annot["MaxEntScan_alt"]) * 100) / float(annot["MaxEntScan_ref"])

                            annotations[-1]["ANN"].append(annot)

                        # app.logger.debug(f"       - Create Variant : {sample}")
                        variant = Variant(id=f"{v.chrom}-{v.pos}-{v.ref}-{v.alt[0]}", chr=v.chrom, pos=v.pos, ref=v.ref, alt=v.alt[0], annotations=annotations)
                        db.session.add(variant)

                    # sample.variants.append(variant)
                    v2s = Var2Sample(variant_ID=variant.id, sample_ID=sample.id, depth=v.getPopDP(), allelic_depth=v.getPopAltAD()[0], filter=v.filter)
                    db.session.add(v2s)

        except Exception as e:
            db.session.remove()
            app.logger.info(f"{type(e).__name__} : {e}")
            sample = Sample.query.get(sample.id)
            sample.status = -1
        else:
            sample.status = 1
            current_file.unlink()
            if interface:
                vcf_path.unlink()
            vcf_vep.unlink()
            stats_vep.unlink()
        finally:
            db.session.commit()
            app.logger.info(f"---- Variant for Sample Added : {sample} - {sample.id} ----")
            path_locker.unlink()
