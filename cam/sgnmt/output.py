"""This module contains the output handlers. These handlers create 
output files from the n-best lists generated by the ``Decoder``. They
can be activated via --outputs.

This module depends on OpenFST to write FST files in binary format. To
enable Python support in OpenFST, use a recent version (>=1.5.4) and 
compile with ``--enable_python``. Further information can be found here:

http://www.openfst.org/twiki/bin/view/FST/PythonExtension 

"""

from abc import abstractmethod
import pywrapfst as fst
import os
import errno
import logging
from cam.sgnmt import utils
import numpy as np
import codecs
from collections import defaultdict


def _mkdir(path, name):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise
        else:
            logging.warn("Output %s directory '%s' already exists." 
                         % (name, path))


class OutputHandler(object):
    """Interface for output handlers. """
    
    def __init__(self):
        """ Empty constructor """
        pass
    
    @abstractmethod
    def write_hypos(self, all_hypos):
        """This method writes output files to the file system. The
        configuration parameters such as output paths should already
        have been provided via constructor arguments.
        
        Args:
            all_hypos (list): list of nbest lists of hypotheses
        
        Raises:
            IOError. If something goes wrong while writing to the disk
        """
        raise NotImplementedError


class TextOutputHandler(OutputHandler):
    """Writes the first best hypotheses to a plain text file """
    
    def __init__(self, path, trg_wmap):
        """Creates a plain text output handler to write to ``path`` """
        super(TextOutputHandler, self).__init__()
        self.path = path
        self.trg_wmap = trg_wmap
        
    def write_hypos(self, all_hypos):
        """Writes the hypotheses in ``all_hypos`` to ``path`` """
        if self.f is not None:
            for hypos in all_hypos:
                self.f.write(utils.apply_trg_wmap(hypos[0].trgt_sentence,
                                                  self.trg_wmap))
                self.f.write("\n")
                self.f.flush()
        else:
            with codecs.open(self.path, "w", encoding='utf-8') as f:
                for hypos in all_hypos:
                    f.write(utils.apply_trg_wmap(hypos[0].trgt_sentence,
                                                 self.trg_wmap))
                    f.write("\n")
                    self.f.flush()

    def open_file(self):
        self.f = codecs.open(self.path, "w", encoding='utf-8')

    def close_file(self):
        self.f.close()

    def write_empty_line(self):
        if self.f is not None:
            self.f.write("\n")
            self.f.flush()


class NBestOutputHandler(OutputHandler):
    """Produces a n-best file in Moses format. The third part of each 
    entry is used to store the separated unnormalized predictor scores.
    Note that the sentence IDs are shifted: Moses n-best files start 
    with the index 0, but in SGNMT and HiFST we usually refer to the 
    first sentence with 1 (e.g. in lattice directories or --range)
    """
    
    def __init__(self, path, predictor_names, start_sen_id, trg_wmap):
        """Creates a Moses n-best list output handler.
        
        Args:
            path (string):  Path to the n-best file to write
            predictor_names: Names of the predictors whose scores
                             should be included in the score breakdown
                             in the n-best list
            start_sen_id: ID of the first sentence
            trg_wmap (dict): (Inverse) word map for target language
        """
        super(NBestOutputHandler, self).__init__()
        self.path = path
        self.start_sen_id = start_sen_id
        self.trg_wmap = trg_wmap
        self.predictor_names = []
        name_count = {}
        for name in predictor_names:
            if not name in name_count:
                name_count[name] = 1
                final_name = name
            else:
                name_count[name] += 1
                final_name = "%s%d" % (name, name_count[name])
            self.predictor_names.append(final_name.replace("_", "0"))
        
    def write_hypos(self, all_hypos):
        """Writes the hypotheses in ``all_hypos`` to ``path`` """
        with codecs.open(self.path, "w", encoding='utf-8') as f:
            n_predictors = len(self.predictor_names)
            idx = self.start_sen_id
            for hypos in all_hypos:
                for hypo in hypos:
                    f.write("%d ||| %s ||| %s ||| %f" %
                            (idx,
                             utils.apply_trg_wmap(hypo.trgt_sentence,
                                                  self.trg_wmap),
                             ' '.join("%s= %f" % (
                                  self.predictor_names[i],
                                  sum([s[i][0] for s in hypo.score_breakdown]))
                                      for i in xrange(n_predictors)),
                             hypo.total_score))
                    f.write("\n")
                idx += 1


class TimeCSVOutputHandler(OutputHandler):
    """Produces one CSV file for each sentence. The CSV files contain
    the predictor score breakdown for each translation prefix length.
    """
    
    def __init__(self, path, predictor_names, start_sen_id):
        """Creates a Moses n-best list output handler.
        
        Args:
            path (string):  Path to the n-best file to write
            predictor_names: Names of the predictors whose scores
                             should be included in the score breakdown
                             in the n-best list
            start_sen_id: ID of the first sentence
        """
        super(TimeCSVOutputHandler, self).__init__()
        self.path = path
        self.file_pattern = path + "/%d.csv" 
        self.start_sen_id = start_sen_id
        self.predictor_names = []
        name_count = {}
        for name in predictor_names:
            if not name in name_count:
                name_count[name] = 1
                final_name = name
            else:
                name_count[name] += 1
                final_name = "%s%d" % (name, name_count[name])
            self.predictor_names.append(final_name)
        
    def write_hypos(self, all_hypos):
        """Writes ngram files for each sentence in ``all_hypos``.
        
        Args:
            all_hypos (list): list of nbest lists of hypotheses
        
        Raises:
            OSError. If the directory could not be created
            IOError. If something goes wrong while writing to the disk
        """
        _mkdir(self.path, "TimeCSV")
        sen_idx = self.start_sen_id
        n_predictors = len(self.predictor_names)
        placeholder = "\t-" * (n_predictors*2)
        for hypos in all_hypos:
            sen_idx += 1
            with open(self.file_pattern % sen_idx, "w") as f:
                hypo_count = len(hypos)
                # Headers
                f.write("Time")
                for i in xrange(hypo_count):
                    f.write("".join(["\t%s-%d" % (n, i+1) 
                                       for n in self.predictor_names]))
                    f.write("".join(["\t%s-%d_weight" % (n, i+1) 
                                       for n in self.predictor_names]))
                f.write("\n")
                max_len = max([len(hypo.trgt_sentence) for hypo in hypos])
                for pos in xrange(max_len+1):
                    f.write(str(pos))
                    for hypo in hypos:
                        if pos >= len(hypo.score_breakdown):
                            f.write(placeholder)
                        else:
                            for pred_idx in xrange(n_predictors):
                                acc_pred_score = sum([s[pred_idx][0] for s in hypo.score_breakdown[:pos+1]])
                                f.write("\t%f" % acc_pred_score)
                            for pred_idx in xrange(n_predictors):
                                f.write("\t%f" % hypo.score_breakdown[pos][pred_idx][1])
                    f.write("\n")


class NgramOutputHandler(OutputHandler):
    """This output handler extracts MBR-style ngram posteriors from the 
    hypotheses returned by the decoder. The hypothesis scores are assumed to
    be loglikelihoods, which we renormalize to make sure that we operate on a
    valid distribution. The scores produced by the output handler are 
    probabilities of an ngram being in the translation.
    """
    
    def __init__(self, path, min_order, max_order, start_sen_id):
        """Creates an ngram output handler.
        
        Args:
            path (string):  Path to the ngram directory to create
            min_order (int):  Minimum order of extracted ngrams
            max_order (int):  Maximum order of extracted ngrams
            start_sen_id (int):  ID of the first sentence
        """
        super(NgramOutputHandler, self).__init__()
        self.path = path
        self.min_order = min_order
        self.max_order = max_order
        self.start_sen_id = start_sen_id
        self.file_pattern = path + "/%d.txt" 
      
    def write_hypos(self, all_hypos):
        """Writes ngram files for each sentence in ``all_hypos``.
        
        Args:
            all_hypos (list): list of nbest lists of hypotheses
        
        Raises:
            OSError. If the directory could not be created
            IOError. If something goes wrong while writing to the disk
        """
        _mkdir(self.path, "ngram")
        sen_idx = self.start_sen_id
        for hypos in all_hypos:
            sen_idx += 1
            total = utils.log_sum([hypo.total_score for hypo in hypos])
            normed_scores = [hypo.total_score - total for hypo in hypos]
            ngrams = defaultdict(dict)
            # Collect ngrams
            for hypo_idx, hypo in enumerate(hypos):
                sen_eos = [utils.GO_ID] + hypo.trgt_sentence + [utils.EOS_ID]
                for pos in xrange(1, len(sen_eos) + 1):
                    hist = sen_eos[:pos]
                    for order in xrange(self.min_order, self.max_order + 1):
                        ngram = ' '.join(map(str, hist[-order:]))
                        ngrams[ngram][hypo_idx] = True
            with open(self.file_pattern % sen_idx, "w") as f:
                for ngram, hypo_indices in ngrams.iteritems():
                    ngram_score = np.exp(utils.log_sum(
                       [normed_scores[hypo_idx] for hypo_idx in hypo_indices]))
                    f.write("%s : %f\n" % (ngram, min(1.0, ngram_score)))


class FSTOutputHandler(OutputHandler):
    """This output handler creates FSTs with with sparse tuple arcs 
    from the n-best lists from the decoder. The predictor scores are 
    kept separately in the sparse tuples. Note that this means that 
    the parameter ``--combination_scheme`` might not be visible in the 
    lattices because predictor scores are not combined. The order in 
    the sparse tuples corresponds to the order of the predictors in 
    the ``--predictors`` argument.
    
    Note that the created FSTs use another ID for UNK to avoid 
    confusion with the epsilon symbol used by OpenFST.
    """
    
    def __init__(self, path, start_sen_id, unk_id):
        """Creates a sparse tuple FST output handler.
        
        Args:
            path (string):  Path to the VECLAT directory to create
            start_sen_id (int):  ID of the first sentence
            unk_id (int): Id which should be used in the FST for UNK
        """
        super(FSTOutputHandler, self).__init__()
        self.path = path
        self.start_sen_id = start_sen_id
        self.unk_id = unk_id
        self.file_pattern = path + "/%d.fst" 
      
    def write_weight(self, score_breakdown):
        """Helper method to create the weight string """
        els = ['0']
        for (idx,score) in enumerate(score_breakdown):
            els.append(str(idx+1))
            # We need to take the negative here since the tropical
            # FST arc type expects negative log probs instead of log probs
            els.append(str(-score[0]))
        return ','.join(els)

    def write_hypos(self, all_hypos):
        """Writes FST files with sparse tuples for each sentence in 
        ``all_hypos``. The created lattices are not optimized in any
        way: We create a distinct path for each entry in 
        ``all_hypos``. We advise you to determinize/minimize them if 
        you are planning to use them for further processing.
        
        Args:
            all_hypos (list): list of nbest lists of hypotheses
        
        Raises:
            OSError. If the directory could not be created
            IOError. If something goes wrong while writing to the disk
        """
        _mkdir(self.path, "FST")
        fst_idx = self.start_sen_id
        for hypos in all_hypos:
            fst_idx += 1
            c = fst.Compiler(arc_type="tropicalsparsetuple")
            # state ID 0 is start, 1 is final state
            next_free_id = 2
            for hypo in hypos:
                syms = hypo.trgt_sentence
                # Connect with start node
                c.write("0\t%d\t%d\t%d\n" % (next_free_id,
                                             utils.GO_ID,
                                             utils.GO_ID))
                next_free_id += 1
                for pos in xrange(len(hypo.score_breakdown)-1):
                    c.write("%d\t%d\t%d\t%d\t%s\n" % (
                            next_free_id-1, # last state id
                            next_free_id, # next state id 
                            syms[pos], syms[pos], # arc labels
                            self.write_weight(hypo.score_breakdown[pos])))
                    next_free_id += 1
                # Connect with final node
                c.write("%d\t1\t%d\t%d\t%s\n" % (
                                next_free_id-1,
                                utils.EOS_ID,
                                utils.EOS_ID,
                                self.write_weight(hypo.score_breakdown[-1])))
            c.write("1\n") # Add final node
            f = c.compile()
            f.write(self.file_pattern % fst_idx)


class StandardFSTOutputHandler(OutputHandler):
    """This output handler creates FSTs with standard arcs. In contrast
    to ``FSTOutputHandler``, predictor scores are combined using 
    ``--combination_scheme``.
    
    Note that the created FSTs use another ID for UNK to avoid 
    confusion with the epsilon symbol used by OpenFST.
    """
    
    def __init__(self, path, start_sen_id, unk_id):
        """Creates a standard arc FST output handler.
        
        Args:
            path (string):  Path to the fst directory to create
            start_sen_id (int):  ID of the first sentence
            unk_id (int): Id which should be used in the FST for UNK
        """
        super(StandardFSTOutputHandler, self).__init__()
        self.path = path
        self.start_sen_id = start_sen_id
        self.unk_id = unk_id
        self.file_pattern = path + "/%d.fst" 
      
    def write_hypos(self, all_hypos):
        """Writes FST files with standard arcs for each
        sentence in ``all_hypos``. The created lattices are not 
        optimized in any way: We create a distinct path for each entry 
        in ``all_hypos``. We advise you to determinize/minimize them if
        you are planning to use them for further processing. 
        
        Args:
            all_hypos (list): list of nbest lists of hypotheses
        
        Raises:
            OSError. If the directory could not be created
            IOError. If something goes wrong while writing to the disk
        """
        _mkdir(self.path, "FST")
        fst_idx = self.start_sen_id
        for hypos in all_hypos:
            fst_idx += 1
            c = fst.Compiler()
            # state ID 0 is start, 1 is final state
            next_free_id = 2
            for hypo in hypos:
                # Connect with start node
                c.write("0\t%d\t%d\t%d\t%f\n" % (next_free_id,
                                                 utils.GO_ID,
                                                 utils.GO_ID,
                                                 -hypo.total_score))
                next_free_id += 1
                for sym in hypo.trgt_sentence:
                    c.write("%d\t%d\t%d\t%d\n" % (next_free_id-1,
                                                  next_free_id,
                                                  sym, sym))
                    next_free_id += 1
                # Connect with final node
                c.write("%d\t1\t%d\t%d\n" % (next_free_id-1,
                                             utils.EOS_ID,
                                             utils.EOS_ID))
            c.write("1\n")
            f = c.compile()
            f.write(self.file_pattern % fst_idx)


class AlignmentOutputHandler(object):
    """Interface for output handlers for alignments. """
    
    def __init__(self):
        """ Empty constructor """
        pass
    
    @abstractmethod
    def write_alignments(self, alignments):
        """This method writes output files to the file system. The
        configuration parameters such as output paths should already
        have been provided via constructor arguments.
        
        Args:
            alignments (list): list of alignment matrices
        
        Raises:
            IOError. If something goes wrong while writing to the disk
        """
        raise NotImplementedError


class CSVAlignmentOutputHandler(AlignmentOutputHandler):
    """Creates a directory with CSV files which store the alignment
    matrices.
    """
    
    def __init__(self, path):
        self.path = path
        self.file_pattern = path + "/%d.csv"
    
    def write_alignments(self, alignments):
        """Writes CSV files for each alignment. 
        
        Args:
            alignments (list): list of alignments
        
        Raises:
            OSError. If the directory could not be created
            IOError. If something goes wrong while writing to the disk
        """
        try:
            os.makedirs(self.path)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise
            else:
                logging.warn(
                        "Output CSV directory %s already exists." % self.path)
        idx = 1
        for alignment in alignments:
            np.savetxt(self.file_pattern % idx, alignment)
            idx += 1


class NPYAlignmentOutputHandler(AlignmentOutputHandler):
    """Creates a directory with alignment matrices in numpy format npy
    """
    
    def __init__(self, path):
        self.path = path
        self.file_pattern = path + "/%d.npy"
    
    def write_alignments(self, alignments):
        """Writes NPY files for each alignment. 
        
        Args:
            alignments (list): list of alignments
        
        Raises:
            OSError. If the directory could not be created
            IOError. If something goes wrong while writing to the disk
        """
        try:
            os.makedirs(self.path)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise
            else:
                logging.warn(
                        "Output NPY directory %s already exists." % self.path)
        idx = 1
        for alignment in alignments:
            np.save(self.file_pattern % idx, alignment)
            idx += 1


class TextAlignmentOutputHandler(AlignmentOutputHandler):
    """Creates a single text alignment file (Pharaoh format).
    """
    
    def __init__(self, path):
        self.path = path
    
    def write_alignments(self, alignments):
        """Writes an alignment file in standard text format. 
        
        Args:
            alignments (list): list of alignments
        
        Raises:
            IOError. If something goes wrong while writing to the disk
        """
        with open(self.path, "w") as f:
            for alignment in alignments:
                src_len,trg_len = alignment.shape
                entries = []
                for spos in xrange(src_len):
                    for tpos in xrange(trg_len):
                        entries.append("%d-%d:%f" % (spos,
                                                     tpos,
                                                     alignment[spos,tpos]))
                f.write("%s\n" % ' '.join(entries))
