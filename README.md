# DrSEUs
## (D)ynamic (r)obust (S)ingle (E)vent (U)pset (s)imulator

Fault injection framework and application for performing CPU fault injection on:

* P2020RDB (Using BDI3000 JTAG debugger)
* ZedBoard (Using BDI3000 JTAG debugger)
* Simics simulation of P2020RDB
* Simics simulation of CoreTile Express A9x4 (Only two cores simulated)

DrSEUs Terminology:

* Campaign: contains gold execution run of target application without fault
            injections that is used for comparison with one or more iterations
* Iteration: monitored execution run of target application with one or more
             injections
* Injection: single bit flip of randomly selected register or TLB entry

Run drseus.py -h for usage information

Usage Example:

* drseus.py -s ppc_fi_2d_conv_fft_omp -a "lena.bmp out.bmp" -f lena.bmp -o out.bmp -c 1000
    * Creates a Simics fault-injection campaign with 1000 checkpoints
    * Runs "ppc_fi_2d_conv_fft_omp lena.bmp out.bmp" on the device under test
    * Checks for output file "out.bmp"
* drseus.py -i -p 8 -n 100
    * Performs 100 injection iterations using 8 processes
* drseus.py -l
    * Starts log server
    * Navigate to http://localhost:8000 in your web browser
