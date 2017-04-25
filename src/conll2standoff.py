#!/usr/bin/env python

# Script to convert a CoNLL-flavored BIO-formatted entity-tagged file
# into BioNLP ST-flavored standoff with reference to the original
# text.

import sys
import re
import os
import codecs
import glob
import lxml.etree as ET



try:
    import psyco
    psyco.full()
except:
    pass

# what to do if an error in the tag sequence (e.g. "O I-T1" or "B-T1
# I-T2") is encountered: recover/discard the erroneously tagged 
# sequence, or abord the entire process
# TODO: add a command-line option for this
SEQUENCE_ERROR_RECOVER, SEQUENCE_ERROR_DISCARD, SEQUENCE_ERROR_FAIL = range(3)

SEQUENCE_ERROR_PROCESSING = SEQUENCE_ERROR_RECOVER

# TODO: get rid of globals

# output goes to stdout by default
out = sys.stdout
reference_directory = None
output_directory = None

def reference_text_filename(fn):
    # Tries to determine the name of the reference text file
    # for the given CoNLL output file.

    fnbase = os.path.basename(fn)
    reffn = os.path.join(reference_directory, fnbase)

    # if the file doesn't exist, try replacing the last dot-separated
    # suffix in the filename with .txt
    if not os.path.exists(reffn):
        reffn = re.sub(r'(.*)\..*', r'\1.txt', reffn)

    return reffn

def output_filename(fn):
    if output_directory is None:
        return None

    reffn = reference_text_filename(fn)
    return os.path.join(output_directory, os.path.basename(reffn).replace(".txt",".a1"))

parser = ET.XMLParser(strip_cdata=False)
def process(fn):
    global out

    xml_folder = get_original_dataset_folders('i2b2deid2014')
    dataset_type = os.path.basename(fn).split('.')[0]

    # ... and the tagged file
    try:
        #tagfile = open(fn)
        tagfile = codecs.open(fn, "rt", "UTF-8")
    except:
        print >> sys.stderr, "ERROR: failed to open file %s" % fn
        raise
    tagtext = tagfile.read()
    tagfile.close()


    # parse CoNLL-X-flavored tab-separated BIO, storing boundaries and
    # tagged tokens. The format is one token per line, with the
    # following tab-separated fields:
    #
    #     START END TOKEN LEMMA POS CHUNK TAG
    #
    # where we're only interested in the start and end offsets
    # (START,END), the token text (TOKEN) for verification, and the
    # NER tags (TAG).  Additionally, sentence boundaries are marked by
    # blank lines in the input.

    currentFilename = ''
    taggedTokens = []
    for ln, l in enumerate(tagtext.split('\n')):
        if l.strip() == '':
            # skip blank lines (sentence boundary markers)
            continue

        fields = l.split()
        assert len(fields) == 4, "Error: expected 7 tab-separated fields on line %d in %s, found %d: %s" % (ln+1, fn, len(fields), l.encode("UTF-8"))

        # TODO: change later
        ttext = fields[0]
        filename = fields[1]
        start_end = fields[2]
        gold_label = fields[-2]
        tag = fields[-1]
        start, end = start_end.split('_')
#         start, end, ttext = fields[0:3]
#         tag = fields[6]
        start, end = int(start), int(end)

        if currentFilename != filename:
            if currentFilename != '':
                output_entities(out, taggedTokens, reftext, fn)
            taggedTokens = []
            currentFilename = filename
#             reffn = reference_text_filename(filename)
        
#             try:
#                 filepaths = glob.glob(os.path.join(xml_output_folder, '*.xml'))
#                 for filepath in filepaths:
            filepath = os.path.join(xml_folder[dataset_type], '{0}.xml'.format(filename))
            tree = ET.parse(filepath, parser)
            xmldoc = tree.getroot()
            reftext = xmldoc.findtext('TEXT')
#             print("reftext: {0}".format(reftext))
#                 reffile = codecs.open(reffn, "rt", "UTF-8")

            # if an output directory is specified, write a file with an
            # appropriate name there
            if output_directory is not None:
#                     outfn = output_filename(fn)
                outfn = os.path.join(output_directory, '{0}.ann'.format(filename))
#                 out = codecs.open(outfn, "wt", "UTF-8")
                out = open(outfn, "wt")
#             except:
#                 print >> sys.stderr, "ERROR: failed to open reference file %s" % filepath
# #                 print >> sys.stderr, "ERROR: failed to open reference file %s" % reffn
#                 raise
#             reftext = reffile.read()
#             reffile.close()
        
        # parse tag
        m = re.match(r'^([BIO])((?:-[A-Za-z_]+)?)$', tag)
        assert m, "ERROR: failed to parse tag '%s' in %s" % (tag, fn)
        ttag, ttype = m.groups()

        # strip off starting "-" from tagged type
        if len(ttype) > 0 and ttype[0] == "-":
            ttype = ttype[1:]

        # sanity check
        assert ((ttype == "" and ttag == "O") or
                (ttype != "" and ttag in ("B","I"))), "Error: tag format '%s' in %s" % (tag, fn)

        # verify that the text matches the original
        try:
            assert reftext[start:end] == ttext, "ERROR: text mismatch for %s on line %d: reference '%s' tagged '%s': %s" % (fn, ln+1, reftext[start:end].encode("UTF-8"), ttext.encode("UTF-8"), l.encode("UTF-8"))
        except:
            print("reftext[start:end]: {0}".format(reftext[start:end].encode("UTF-8")))
            print("ttext: {0}".format(ttext.encode("UTF-8")))
            if reftext[start:end][0] != ttext[0] and reftext[start:end][-1] != ttext[-1]:
                raise AssertionError

        # store tagged token as (begin, end, tag, tagtype) tuple.
        taggedTokens.append((start, end, ttag, ttype))

    # transform input text from CoNLL-X flavored tabbed BIO format to
    # inline-tagged BIO format for processing (this is a bit
    # convoluted, sorry; this script written as a modification of an
    # inline-format BIO conversion script).
    output_entities(out, taggedTokens, reftext, fn)

def output_entities(out, taggedTokens, reftext, fn):
    ### Output for entities ###

    # returns a string containing annotation in the output format
    # for an Entity with the given properties.
    def entityStr(startOff, endOff, eType, idNum, fullText):
        # sanity checks: the string should not contain newlines and
        # should be minimal wrt surrounding whitespace
        eText = fullText[startOff:endOff]
#         assert "\n" not in eText, "ERROR: newline in entity in %s: '%s'" % (fn, eText)
#         assert eText == eText.strip(), "ERROR: entity contains extra whitespace in %s: '%s'" % (fn, eText)
        return "T%d\t%s %d %d\t%s" % (idNum, eType, startOff, endOff, eText)

    idIdx = 1
    prevTag, prevEnd = "O", 0
    currType, currStart = None, None
    for startoff, endoff, ttag, ttype in taggedTokens:

        # special case for surviving format errors in input: if the
        # type sequence changes without a "B" tag, change the tag
        # to allow some output (assumed to be preferable to complete
        # failure.)
        if prevTag != "O" and ttag == "I" and currType != ttype:
            if SEQUENCE_ERROR_PROCESSING == SEQUENCE_ERROR_RECOVER:
                # reinterpret as the missing "B" tag.
                ttag = "B"
            elif SEQUENCE_ERROR_PROCESSING == SEQUENCE_ERROR_DISCARD:
                ttag = "O"
            else:
                assert SEQUENCE_ERROR_PROCESSING == SEQUENCE_ERROR_FAIL
                pass # will fail on later check

        # similarly if an "I" tag occurs after an "O" tag
        if prevTag == "O" and ttag == "I":
            if SEQUENCE_ERROR_PROCESSING == SEQUENCE_ERROR_RECOVER:
                ttag = "B"            
            elif SEQUENCE_ERROR_PROCESSING == SEQUENCE_ERROR_DISCARD:
                ttag = "O"
            else:
                assert SEQUENCE_ERROR_PROCESSING == SEQUENCE_ERROR_FAIL
                pass # will fail on later check

        if prevTag != "O" and ttag != "I":
            # previous entity does not continue into this tag; output
            assert currType is not None and currStart is not None, "ERROR at %s (%d-%d) in %s" % (reftext[startoff:endoff], startoff, endoff, fn)
            
            print(entityStr(currStart, prevEnd, currType, idIdx, reftext).encode("UTF-8"))
            print >> out, entityStr(currStart, prevEnd, currType, idIdx, reftext).encode("UTF-8")

            idIdx += 1

            # reset current entity
            currType, currStart = None, None

        elif prevTag != "O":
            # previous entity continues ; just check sanity
            assert ttag == "I", "ERROR in %s" % fn
            assert currType == ttype, "ERROR: entity of type '%s' continues as type '%s' in %s" % (currType, ttype, fn)
            
        if ttag == "B":
            # new entity starts
            currType, currStart = ttype, startoff
            
        prevTag, prevEnd = ttag, endoff

    # if there's an open entity after all tokens have been processed,
    # we need to output it separately
    if prevTag != "O":
        print(entityStr(currStart, prevEnd, currType, idIdx, reftext).encode("UTF-8"))
        print >> out, entityStr(currStart, prevEnd, currType, idIdx, reftext).encode("UTF-8")

    if output_directory is not None:
        # we've opened a specific output for this
        out.close()

def get_dataset_folder_original(model='crf'):
    if model=='ann':
        return os.path.join('..', '..', 'data', 'datasets', 'original')
    elif model == 'crf':
        return os.path.join('..', '..', 'ner-deid', 'data', 'datasets', 'original')
        
def get_original_dataset_folders(dataset_base_filename, split='60_40', model='crf'):
    folder = {'train':[], 'dev':[], 'test':[]}
    dataset_folder_original = get_dataset_folder_original(model=model)
#     print("dataset_folder_original: {0}".format(dataset_folder_original))
#     print("split: {0}".format(split))
#     print("dataset_base_filename: {0}".format(dataset_base_filename))
    folder['train'] = os.path.join(dataset_folder_original, dataset_base_filename, split, 'training-PHI-Gold-Set1')
#     filepaths['train'] = sorted(glob.glob(os.path.join(train_folder, '*.xml')))
    folder['dev'] = os.path.join(dataset_folder_original, dataset_base_filename, split, 'training-PHI-Gold-Set2')
#     filepaths['dev'] = sorted(glob.glob(os.path.join(train_folder, '*.xml')))
    folder['test'] = os.path.join(dataset_folder_original, dataset_base_filename, split, 'testing-PHI-Gold-fixed')
#     filepaths['test'] = sorted(sorted(glob.glob(os.path.join(test_folder, '*.xml')))) 
    return folder

def get_original_dataset_filepaths(dataset_base_filename, split='60_40', model='crf'):
    filepaths = {'train':[], 'dev':[], 'test':[]}
    dataset_folder_original = get_dataset_folder_original(model=model)
#     print("dataset_folder_original: {0}".format(dataset_folder_original))
#     print("split: {0}".format(split))
#     print("dataset_base_filename: {0}".format(dataset_base_filename))
    train_folder = os.path.join(dataset_folder_original, dataset_base_filename, split, 'training-PHI-Gold-Set1')
    filepaths['train'] = sorted(glob.glob(os.path.join(train_folder, '*.xml')))
    train_folder = os.path.join(dataset_folder_original, dataset_base_filename, split, 'training-PHI-Gold-Set2')
    filepaths['dev'] = sorted(glob.glob(os.path.join(train_folder, '*.xml')))
    test_folder = os.path.join(dataset_folder_original, dataset_base_filename, split, 'testing-PHI-Gold-fixed')
    filepaths['test'] = sorted(sorted(glob.glob(os.path.join(test_folder, '*.xml')))) 
    return filepaths


def main(argv):
    global reference_directory, output_directory


    # (clumsy arg parsing, sorry)

    # Take a mandatory "-d" arg that tells us where to find the original,
    # unsegmented and untagged reference files.

    if len(argv) < 3 or argv[1] != "-d":
        print >> sys.stderr, "USAGE:", argv[0], "-d REF-DIR [-o OUT-DIR] (FILES|DIR)"
        return 1

    reference_directory = argv[2]

    # Take an optional "-o" arg specifying an output directory for the results

    output_directory = None
    filenames = argv[3:]
    if len(argv) > 4 and argv[3] == "-o":
        output_directory = argv[4]
        if not os.path.exists(output_directory):
            os.makedirs(output_directory)
        print >> sys.stderr, "Writing output to %s" % output_directory
        filenames = argv[5:]

    print("filenames: {0}".format(filenames))

    # special case: if we only have a single file in input and it specifies
    # a directory, process all files in that directory
    input_directory = None
    if len(filenames) == 1 and os.path.isdir(filenames[0]):
        input_directory = filenames[0]
        filenames = [os.path.join(input_directory, fn) for fn in os.listdir(input_directory)]
        print >> sys.stderr, "Processing %d files in %s ..." % (len(filenames), input_directory)

    fail_count = 0
    for fn in filenames:
        process(fn)
#         try:
#             process(fn)
#         except Exception, e:
#             print >> sys.stderr, "Error processing %s: %s" % (fn, e)
#             fail_count += 1
# 
#             # if we're storing output on disk, remove the output file
#             # to avoid having partially-written data
#             ofn = output_filename(fn)
#             try:
#                 os.remove(ofn)
#             except:
#                 # never mind if that fails
#                 pass

    if fail_count > 0:
        print >> sys.stderr, """
##############################################################################
#
# WARNING: error in processing %d/%d files, output is incomplete!
#
##############################################################################
""" % (fail_count, len(filenames))

    return 0

if __name__ == "__main__":
    source = '/Users/jjylee/Documents/workspace/nlp/ner-deid/src/ann/data/i2b2deid2014/stanford/60_40'
    target = '/Users/jjylee/Documents/workspace/nlp/brat-master/tools/out/train'
    filename = '/Users/jjylee/Documents/workspace/nlp/ner-deid/src/ann/data/i2b2deid2014/stanford/60_40/train.txt'
#     source = '/Users/jjylee/Documents/workspace/nlp/ner-deid/src/ann/data/conll2003/stanford/140_20_40'
#     target = '/Users/jjylee/Documents/workspace/nlp/brat-master/tools/out/train'
#     filename = '/Users/jjylee/Documents/workspace/nlp/ner-deid/src/ann/dat/conll2003/stanford/140_20_40/train.txt'
    args = ['', '-d', source, '-o', target, filename]
    main(args)
#     sys.exit(main(sys.argv))
