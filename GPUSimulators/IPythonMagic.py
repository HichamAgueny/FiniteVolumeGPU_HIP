# -*- coding: utf-8 -*-

"""
This python module implements helpers for IPython / Jupyter and CUDA

Copyright (C) 2018  SINTEF ICT

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import logging
import gc

from IPython.core import magic_arguments
from IPython.core.magic import line_magic, Magics, magics_class
#import pycuda.driver as cuda
from hip import hip, hiprtc

from GPUSimulators import Common, CudaContext

def hip_check(call_result):
    err = call_result[0]
    result = call_result[1:]
    if len(result) == 1:
        result = result[0]
    if isinstance(err, hip.hipError_t) and err != hip.hipError_t.hipSuccess:
        raise RuntimeError(str(err))
    elif (
        isinstance(err, hiprtc.hiprtcResult)
        and err != hiprtc.hiprtcResult.HIPRTC_SUCCESS
    ):
        raise RuntimeError(str(err))
    return result

@magics_class
class MagicCudaContext(Magics): 
    @line_magic
    @magic_arguments.magic_arguments()
    @magic_arguments.argument(
        'name', type=str, help='Name of context to create')
    @magic_arguments.argument(
        '--blocking', '-b', action="store_true", help='Enable blocking context')
    @magic_arguments.argument(
        '--no_cache', '-nc', action="store_true", help='Disable caching of kernels')
    @magic_arguments.argument(
        '--no_autotuning', '-na', action="store_true", help='Disable autotuning of kernels')

    def cuda_context_handler(self, line):
        args = magic_arguments.parse_argstring(self.cuda_context_handler, line)
        self.logger =  logging.getLogger(__name__)
        
        self.logger.info("Registering %s in user workspace", args.name)
        
        context_flags = None
        if (args.blocking):
            #context_flags = cuda.ctx_flags.SCHED_BLOCKING_SYNC
            context_flags = hip_check(hip.hipSetDeviceFlags(hip.hipDeviceScheduleBlockingSync))
        
        if args.name in self.shell.user_ns.keys():
            self.logger.debug("Context already registered! Ignoring")
            return
        else:
            self.logger.debug("Creating context")
            use_cache = False if args.no_cache else True
            use_autotuning = False if args.no_autotuning else True
            self.shell.user_ns[args.name] = CudaContext.CudaContext(context_flags=context_flags, use_cache=use_cache, autotuning=use_autotuning)
        
        # this function will be called on exceptions in any cell
        def custom_exc(shell, etype, evalue, tb, tb_offset=None):
            self.logger.exception("Exception caught: Resetting to CUDA context %s", args.name)
            #while (cuda.Context.get_current() != None):
            while (hip.hipCtxGetCurrent() != None):    
                #context = cuda.Context.get_current()
                context = hip_check(hip.hipCtxGetCurrent())
                self.logger.info("Popping <%s>", str(context.handle))
                #cuda.Context.pop()
                hip.hipCtxPopCurrent()
            if args.name in self.shell.user_ns.keys():
                self.logger.info("Pushing <%s>", str(self.shell.user_ns[args.name].cuda_context.handle))
                self.shell.user_ns[args.name].cuda_context.push()
            else:
                self.logger.error("No CUDA context called %s found (something is wrong)", args.name)
                self.logger.error("CUDA will not work now")

            self.logger.debug("==================================================================")
            
            # still show the error within the notebook, don't just swallow it
            shell.showtraceback((etype, evalue, tb), tb_offset=tb_offset)

        # this registers a custom exception handler for the whole current notebook
        get_ipython().set_custom_exc((Exception,), custom_exc)
        
        
        # Handle CUDA context when exiting python
        import atexit
        def exitfunc():
            self.logger.info("Exitfunc: Resetting CUDA context stack")
            #while (cuda.Context.get_current() != None):
            while (hip.hipCtxGetCurrent() != None):    
                #context = cuda.Context.get_current()
                context = hip_check(hip.hipCtxGetCurrent())
                self.logger.info("`-> Popping <%s>", str(context.handle))
                #cuda.Context.pop()
                hip.hipCtxPopCurrent()
            self.logger.debug("==================================================================")
        atexit.register(exitfunc)
        
        
        
        
        
        
        
        
@magics_class
class MagicLogger(Magics): 
    logger_initialized = False
    
    @line_magic
    @magic_arguments.magic_arguments()
    @magic_arguments.argument(
        'name', type=str, help='Name of context to create')
    @magic_arguments.argument(
        '--out', '-o', type=str, default='output.log', help='The filename to store the log to')
    @magic_arguments.argument(
        '--level', '-l', type=int, default=20, help='The level of logging to screen [0, 50]')
    @magic_arguments.argument(
        '--file_level', '-f', type=int, default=10, help='The level of logging to file [0, 50]')
    def setup_logging(self, line):
        if (self.logger_initialized):
            logging.getLogger('GPUSimulators').info("Global logger already initialized!")
            return;
        else:
            self.logger_initialized = True
            
            args = magic_arguments.parse_argstring(self.setup_logging, line)
            import sys
            
            #Get root logger
            logger = logging.getLogger('GPUSimulators')
            logger.setLevel(min(args.level, args.file_level))

            #Add log to screen
            ch = logging.StreamHandler()
            ch.setLevel(args.level)
            logger.addHandler(ch)
            logger.log(args.level, "Console logger using level %s", logging.getLevelName(args.level))
            
            #Get the outfilename (try to evaluate if Python expression...)
            try:
                outfile = eval(args.out, self.shell.user_global_ns, self.shell.user_ns)
            except:
                outfile = args.out
            
            #Add log to file
            logger.log(args.level, "File logger using level %s to %s", logging.getLevelName(args.file_level), outfile)
            
            fh = logging.FileHandler(outfile)
            formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s: %(message)s')
            fh.setFormatter(formatter)
            fh.setLevel(args.file_level)
            logger.addHandler(fh)
        
        logger.info("Python version %s", sys.version)
        self.shell.user_ns[args.name] = logger



        


@magics_class
class MagicMPI(Magics): 
    
    @line_magic
    @magic_arguments.magic_arguments()
    @magic_arguments.argument(
        'name', type=str, help='Name of context to create')
    @magic_arguments.argument(
        '--num_engines', '-n', type=int, default=4, help='Number of engines to start')
    def setup_mpi(self, line):
        args = magic_arguments.parse_argstring(self.setup_mpi, line)
        logger = logging.getLogger('GPUSimulators')
        if args.name in self.shell.user_ns.keys():
            logger.warning("MPI alreay set up, resetting")
            self.shell.user_ns[args.name].shutdown()
            self.shell.user_ns[args.name] = None
            gc.collect()
        self.shell.user_ns[args.name] = Common.IPEngine(args.num_engines)

        






# Register 
ip = get_ipython()
ip.register_magics(MagicCudaContext)
ip.register_magics(MagicLogger)
ip.register_magics(MagicMPI)

