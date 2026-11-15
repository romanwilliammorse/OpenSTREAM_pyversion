classdef CoolPropWrapper < handle
    %CoolPropWrapper MATLAB interface to the CoolProp thermophysical property library.
    %
    %   The CoolPropWrapper class provides a MATLAB interface to the CoolProp
    %   thermophysical property library through Python's CoolProp AbstractState
    %   interface. It enables the calculation of thermodynamic and transport
    %   properties of fluids from specified pairs of thermodynamic state
    %   variables.
    %
    %   The class supports configurable fluids, equation-of-state backends,
    %   phase specification, and output formats. Property calculations can be
    %   performed over combinations of input vectors, returning either a
    %   multidimensional matrix of results or paired vector results.
    %
    %   Supported properties include temperature, pressure, enthalpy, entropy,
    %   density, thermal conductivity, dynamic viscosity, specific heat
    %   capacities, Prandtl number, surface tension, phase, and vapor quality.
    %   Saturation temperature and pressure can also be calculated from
    %   pressure and temperature, respectively.
    %
    %   The class manages the Python CoolProp interface and supports object
    %   serialization by restoring Python handles when deserializing objects.
    %
    %   CoolPropWrapper Properties:
    %       fluid           - Working fluid name.
    %       AbstractStateSrc - CoolProp equation-of-state backend.
    %       params          - Available CoolProp parameter names.
    %       outputMode      - Output format ('mat' or 'vec').
    %
    %   CoolPropWrapper Methods:
    %       setFluid            - Change the working fluid.
    %       setAbstractStateSrc - Select the equation-of-state backend.
    %       setOutputMode       - Select the output format.
    %       setPhase            - Specify the thermodynamic phase.
    %       temperature         - Calculate temperature.
    %       pressure            - Calculate pressure.
    %       enthalpy             - Calculate specific enthalpy.
    %       entropy              - Calculate specific entropy.
    %       density              - Calculate mass density.
    %       conductivity         - Calculate thermal conductivity.
    %       viscosity            - Calculate dynamic viscosity.
    %       cp                   - Calculate specific heat at constant pressure.
    %       cv                   - Calculate specific heat at constant volume.
    %       prandtl              - Calculate the Prandtl number.
    %       surfaceTension       - Calculate surface tension.
    %       phase                - Determine the thermodynamic phase.
    %       quality              - Calculate vapor quality.
    %       TsatP                - Calculate saturation temperature from pressure.
    %       PsatT                - Calculate saturation pressure from temperature.
    %
    %   See also: CoolProp, pyenv
    
    properties
        %fluid Working fluid name.
        %   Character vector or string specifying the fluid for which
        %   thermodynamic and transport properties are calculated.
        %   Defaults to 'Water'.
        fluid = 'Water'
        
        %AbstractStateSrc CoolProp equation-of-state backend.
        %   Character vector or string specifying the CoolProp backend
        %   used to evaluate fluid properties. Supported values are:
        %       'HEOS'         - Helmholtz Equation of State.
        %       'TTSE&HEOS'    - Tabular Taylor Series Expansion with HEOS.
        %       'BICUBIC&HEOS' - Bicubic interpolation with HEOS.
        %   Defaults to 'TTSE&HEOS'.
        AbstractStateSrc = 'TTSE&HEOS';

        %params Available CoolProp parameter names.
        %   String array containing the parameter names retrieved from
        %   the CoolProp library.
        params

        %outputMode Property calculation output format.
        %   Character vector specifying how calculated properties are
        %   returned:
        %       'mat' - Return results as a matrix over combinations of
        %               the input values.
        %       'vec' - Return results for paired input values, with
        %               scalar expansion when one input is scalar.
        %   Defaults to 'mat'.
        outputMode = 'mat'
    end

    properties (Transient)
        %inputPairType CoolProp input pair identifier.
        %   Python CoolProp enumeration identifying the thermodynamic
        %   input pair used to update the AbstractState.
        inputPairType

        %CoolPropHandle Python CoolProp module handle.
        %   Python handle to the imported CoolProp module, used to access
        %   the AbstractState interface and related constants.
        CoolPropHandle      % ie. py.CoolProp
        
        %CoolProp CoolProp AbstractState handle.
        %   Python handle to the CoolProp AbstractState instance used
        %   to calculate thermodynamic and transport properties for
        %   the selected fluid and equation-of-state backend.
        CoolProp            % ie. py.CoolProp.AbstactState(...)
    end

    properties (Access=protected)
        as_phase        
    end
    
    methods
        function obj = CoolPropWrapper(fluidName)
            %CoolPropWrapper Create a CoolPropWrapper instance.
            %   OBJ = CoolPropWrapper() creates an instance using Water as
            %   the working fluid and initializes the CoolProp Python
            %   interface.
            %
            %   OBJ = CoolPropWrapper(FLUIDNAME) creates an instance for
            %   the specified working fluid.
            %
            %   The constructor initializes the CoolProp AbstractState
            %   using the configured equation-of-state backend and
            %   retrieves the available CoolProp parameter names.
            %
            %   If CoolProp cannot be imported, the constructor attempts
            %   to assist with Python configuration and installation.
            %
            %   Inputs:
            %       fluidName - Name of the working fluid.
            %                   Defaults to 'Water'.
            %
            %   Outputs:
            %       obj - Initialized CoolPropWrapper instance.
            
            arguments
                fluidName = 'Water'
            end
            
            obj.fluid = fluidName;
            
            try
                obj.CoolPropHandle = py.importlib.import_module('CoolProp');
                obj.setFluid(obj.fluid);
                obj.getCoolPropParameters();
            catch ME
                
                warning(ME.message);
                e=pyenv;
               if ~isempty(e)
                    res = questdlg('A python module has been found, but CoolProp might have not been installed. Should I install it?',...
                                    'Install CoolProp?','Yes','No','Yes');
                    if strcmp('Yes',res)
                        % Locate +CoolPropWrapper directory
                        coolpropwrapper_dir = what('+CoolPropWrapper');
                        
                        % Error if +CoolPropWrapper dir cannot be found
                        if isempty(coolpropwrapper_dir)
                            error('Cannot find +CoolPropWrapper directory');
                        end

                        % Error if multiple +CoolPropWrapper dirs are found
                        if numel(loc) > 1
                            error('Multiple +CoolPropWrapper directories found');
                        end
                            
                        % Retrieve +CoolPropWrapper path
                        coolpropwrapper_dir = coolpropwrapper_dir.path;
                        python_pip_req_path = string(fullfile(coolpropwrapper_dir, 'requirements.txt'));

                        install_code = system(e.Executable+" -m pip install --user -U -r """+ python_pip_req_path + """");

                        if install_code == 0
                            warning('CoolProp was installed successfully.')
                        else
                            error('Python pip install failed.')
                        end                        
                    else
                        warning('Please install CoolProp and/or restart MATLAB.');
                    end
               else
                   
                   % Find the python executable
                   if ispc()
                       % CMD is the default shell. Using `where`
                       query_cmd = 'where python';
                   else % if isunix()
                       % `which` should be available on unix systems 
                       query_cmd = 'which python';
                   end

                   % Perform query
                   [query_code, query_res] = system(query_cmd);
                   % Non-zero exit code means notfound.
                   if query_code ~= 0
                       error('No python on system PATH');
                   end
                   % Split response by \n
                   query_res = strsplit(query_res, '\n');
                   % Choose the first split result
                   pythonPath = query_res{1};
                   
                   try
                       pyenv(pythonPath);
                   catch
                        disp('Python version info:')
                        pyenv
                   end

                   warning('Not sure what happened. Verify Python v3.9+ and the Coolprop Library are installed.');
                   warning('Your currently configured Python is installed <a href="matlab:%s">HERE</a>.',fileparts(pythonPath));
                   warning('For more info: <a href="http://www.coolprop.org/coolprop/wrappers/MATLAB/index.html">http://www.coolprop.org/coolprop/wrappers/MATLAB/index.html</a>.');
                   warning('Ensure a compatible Python version is installed: <a href="https://www.mathworks.com/support/requirements/python-compatibility.html">https://www.mathworks.com/support/requirements/python-compatibility.html</a>.')
                   error('Stopping now.');
                end
                    
            end
            
        end

        function setAbstractStateSrc(obj, src)
            %setAbstractStateSrc Set the CoolProp equation-of-state backend.
            %   setAbstractStateSrc(OBJ, SRC) sets the backend used to
            %   calculate thermodynamic and transport properties.
            %
            %   Supported backends:
            %       'HEOS'         - Helmholtz Equation of State.
            %       'TTSE&HEOS'    - Tabular Taylor Series Expansion.
            %       'BICUBIC&HEOS' - Bicubic interpolation.
            %
            %   The backend is reset to the selected value and the
            %   AbstractState is reinitialized for the current fluid.
            %
            %   SRC may also be 'DEFAULT' or 'RESET' to restore the
            %   default backend, 'TTSE&HEOS'.
            %
            %   Inputs:
            %       src - Backend identifier.
            %
            %   See also: setFluid
            arguments
                obj
                src {mustBeMember(src,{'HEOS','TTSE&HEOS','BICUBIC&HEOS'})}
            end
            src = upper(src);
            switch src
                case {'HEOS','TTSE&HEOS','BICUBIC&HEOS'}
                    obj.AbstractStateSrc = src;
                    obj.setFluid(obj.fluid);
                case {'DEFAULT','RESET'}
                    obj.AbstractStateSrc = 'TTSE&HEOS';
                    obj.setFluid(obj.fluid);
                otherwise
                    error('%s is not a valid Abstract State source\n',...
                                src);
            end
        end

        function setFluid(obj, fluidName)
            %setFluid Set the working fluid.
            %   setFluid(OBJ, FLUIDNAME) changes the working fluid and
            %   initializes a new CoolProp AbstractState for the selected
            %   fluid using the currently configured backend.
            %
            %   Inputs:
            %       fluidName - Name of the working fluid.
            %
            %   See also: setAbstractStateSrc
            try
                obj.fluid = fluidName;
                obj.CoolProp = ...
                    obj.CoolPropHandle.AbstractState(obj.AbstractStateSrc, obj.fluid);
            catch ME
                warning(ME.message);
            end
        end
        
        function setOutputMode(obj, outputMode)
            %setOutputMode Set the property calculation output format.
            %   setOutputMode(OBJ, OUTPUTMODE) selects the format used
            %   when returning calculated properties.
            %
            %   Supported modes:
            %       'mat' - Return results over combinations of input
            %               values as a matrix.
            %       'vec' - Return results for paired input values,
            %               with scalar expansion when applicable.
            %
            %   Inputs:
            %       outputMode - Output format identifier.
            %
            %   See also: property
            switch lower(outputMode)
                case 'mat'
                    obj.outputMode = 'mat';
                case 'vec'
                    obj.outputMode = 'vec';
                otherwise
                    error('Invalid output mode. [mat|vec]');
            end
        end

        function setPhase(obj, phase)
            %setPhase Specify the thermodynamic phase.
            %   setPhase(OBJ, PHASE) specifies the thermodynamic phase
            %   imposed on the CoolProp AbstractState.
            %
            %   This method is an alias for setSpecifyPhase.
            %
            %   Inputs:
            %       phase - Phase identifier, such as 'liquid' or 'gas'.
            %               An empty value clears the phase specification.
            %
            %   See also: setSpecifyPhase, getSpecifyPhase
            obj.setSpecifyPhase(phase)
        end

        function setSpecifyPhase(obj, phase)
            %setSpecifyPhase Set or clear the imposed thermodynamic phase.
            %   setSpecifyPhase(OBJ, PHASE) specifies the thermodynamic
            %   phase imposed on the CoolProp AbstractState.
            %
            %   Supported phase identifiers include:
            %       'liquid'   - Liquid phase.
            %       'gas'      - Gas phase.
            %       'twophase' - Two-phase region.
            %
            %   If PHASE is omitted or empty, no phase is imposed.
            %
            %   Inputs:
            %       phase - Thermodynamic phase identifier.
            %
            %   See also: setPhase, getSpecifyPhase

            arguments
                obj
                phase = ""
            end
            
            phase = obj.scrubInput(phase);
            obj.as_phase = phase;
            switch phase
               case 'liquid'
                   phase = obj.CoolPropHandle.iphase_liquid;
                case 'gas'
                    phase = obj.CoolPropHandle.iphase_gas;
                case 'twophase'
                    phase = obj.CoolPropHandle.iphase_twophase;
                otherwise
                    phase = obj.CoolPropHandle.iphase_not_imposed;
            end
            obj.CoolProp.specify_phase(phase);
            
        end

        function phase = getSpecifyPhase(obj)
            %getSpecifyPhase Get the current CoolProp phase.
            %   PHASE = getSpecifyPhase(OBJ) returns the thermodynamic
            %   phase reported by the CoolProp AbstractState as a
            %   character vector.
            %
            %   Outputs:
            %       phase - Thermodynamic phase identifier.
            %
            %   See also: setSpecifyPhase, phase
            phase = obj.CoolProp.phase();
            phase = obj.phaseEnum2str(phase);
        end
        
        function T = temperature(obj,Atype,A,Btype,B)
            %temperature Calculate temperature.
            %   T = temperature(OBJ, ATYPE, A, BTYPE, B) calculates
            %   temperature for the specified thermodynamic state or
            %   states.
            %
            %   Outputs:
            %       T - Temperature in K.
            %
            %   See also: property, pressure, enthalpy
            T = obj.property(Atype,A,Btype,B,{'t'});
        end
        
        function P = pressure(obj,Atype,A,Btype,B)
             %pressure Calculate pressure.
        %   P = pressure(OBJ, ATYPE, A, BTYPE, B) calculates
        %   pressure for the specified thermodynamic state or
        %   states.
        %
        %   Outputs:
        %       P - Pressure in Pa.
        %
        %   See also: property, temperature, density
            P = obj.property(Atype,A,Btype,B,{'p'});
        end


        function h = enthalpy(obj,Atype,A,Btype,B)
            %enthalpy Calculate specific enthalpy.
            %   H = enthalpy(OBJ, ATYPE, A, BTYPE, B) calculates the
            %   mass-specific enthalpy for the specified thermodynamic
            %   state or states.
            %
            %   Outputs:
            %       h - Mass-specific enthalpy in J/kg.
            %
            %   See also: property
            h = obj.property(Atype,A,Btype,B,{'h'});
        end
        
        function s = entropy(obj,Atype,A,Btype,B)
            %entropy Calculate specific entropy.
            %   S = entropy(OBJ, ATYPE, A, BTYPE, B) calculates the
            %   mass-specific entropy for the specified thermodynamic
            %   state or states.
            %
            %   Outputs:
            %       s - Mass-specific entropy in J/(kg*K).
            %
            %   See also: property
            s = obj.property(Atype,A,Btype,B,{'s'});
        end

        function rho = density(obj,Atype,A,Btype,B)
            %density Calculate mass density.
            %   RHO = density(OBJ, ATYPE, A, BTYPE, B) calculates the
            %   mass density for the specified thermodynamic state
            %   or states.
            %
            %   Outputs:
            %       rho - Mass density in kg/m^3.
            %
            %   See also: property, pressure
            rho = obj.property(Atype,A,Btype,B,{'rho'});
        end

        function k = conductivity(obj,Atype,A,Btype,B)
            %conductivity Calculate thermal conductivity.
            %   K = conductivity(OBJ, ATYPE, A, BTYPE, B) calculates
            %   the thermal conductivity for the specified
            %   thermodynamic state or states.
            %
            %   Outputs:
            %       k - Thermal conductivity in W/(m*K).
            %
            %   See also: property, viscosity, prandtl
            k = obj.property(Atype,A,Btype,B,{'k'}); 
        end

        function mu = viscosity(obj,Atype,A,Btype,B)
            %viscosity Calculate dynamic viscosity.
            %   MU = viscosity(OBJ, ATYPE, A, BTYPE, B) calculates
            %   the dynamic viscosity for the specified
            %   thermodynamic state or states.
            %
            %   Outputs:
            %       mu - Dynamic viscosity in Pa*s.
            %
            %   See also: property, conductivity, prandtl
            mu = obj.property(Atype,A,Btype,B,{'mu'}); 
        end

        function cp = cp(obj,Atype,A,Btype,B)
            %cp Calculate specific heat capacity at constant pressure.
            %   CP = cp(OBJ, ATYPE, A, BTYPE, B) calculates the
            %   mass-specific heat capacity at constant pressure for
            %   the specified thermodynamic state or states.
            %
            %   Outputs:
            %       cp - Specific heat capacity in J/(kg*K).
            %
            %   See also: property, cv
            cp = obj.property(Atype,A,Btype,B,{'cp'}); 
        end

        function cv = cv(obj,Atype,A,Btype,B)
            %cv Calculate specific heat capacity at constant volume.
            %   CV = cv(OBJ, ATYPE, A, BTYPE, B) calculates the
            %   mass-specific heat capacity at constant volume for
            %   the specified thermodynamic state or states.
            %
            %   Outputs:
            %       cv - Specific heat capacity in J/(kg*K).
            %
            %   See also: property, cp
            cv = obj.property(Atype,A,Btype,B,{'cv'}); 
        end

        function pr = prandtl(obj,Atype,A,Btype,B)
            %prandtl Calculate the Prandtl number.
            %   PR = prandtl(OBJ, ATYPE, A, BTYPE, B) calculates the
            %   Prandtl number for the specified thermodynamic state
            %   or states.
            %
            %   Outputs:
            %       pr - Dimensionless Prandtl number.
            %
            %   See also: property, conductivity, viscosity
            pr = obj.property(Atype,A,Btype,B,{'pr'}); 
        end

        function gamma = surfaceTension(obj,Atype,A,Btype,B)
            %surfaceTension Calculate surface tension.
            %   GAMMA = surfaceTension(OBJ, ATYPE, A, BTYPE, B)
            %   calculates the surface tension for the specified
            %   thermodynamic state or states.
            %
            %   When using the TTSE&HEOS or BICUBIC&HEOS backend,
            %   the method temporarily switches to HEOS to perform
            %   the calculation and then restores the original backend.
            %
            %   Outputs:
            %       gamma - Surface tension in N/m.
            %
            %   See also: property, conductivity, viscosity

            currAbstractStateSrc = obj.AbstractStateSrc;
            if strcmp(currAbstractStateSrc, obj.EOS.BICUBIC_HEOS) || ...
                strcmp(currAbstractStateSrc, obj.EOS.TTSE_HEOS)
                obj.setAbstractStateSrc(obj.EOS.HEOS);
            end
            gamma = obj.property(Atype,A,Btype,B,{'gamma'}); 
            obj.setAbstractStateSrc(currAbstractStateSrc)
        end

        function phase = phase(obj,Atype,A,Btype,B)
            %phase Determine the thermodynamic phase.
            %   PHASE = phase(OBJ, ATYPE, A, BTYPE, B) determines the
            %   phase for the specified thermodynamic state or states.
            %
            %   Outputs:
            %       phase - CoolProp phase identifier.
            %
            %   See also: property getSpecifyPhase, quality
            phase = obj.property(Atype,A,Btype,B,{'ph'});
        end
        function quality = quality(obj,Atype,A,Btype,B)
            %quality Calculate vapor quality.
            %   QUALITY = quality(OBJ, ATYPE, A, BTYPE, B) calculates
            %   the vapor quality for the specified thermodynamic
            %   state or states.
            %
            %   Outputs:
            %       quality - Vapor quality, where applicable.
            %
            %   See also: property, phase, TsatP, PsatT
            quality = obj.property(Atype,A,Btype,B,{'Q'});
        end
        function Tsat = TsatP(obj,P)
            %TsatP Calculate saturation temperature from pressure.
            %   TSAT = TsatP(OBJ, P) calculates the saturation
            %   temperature corresponding to the specified pressure
            %   values using a vapor quality of zero.
            %
            %   Inputs:
            %       P - Pressure values in Pa.
            %
            %   Outputs:
            %       Tsat - Saturation temperature in K.
            %
            %   See also: property, PsatT
            Tsat = obj.property('p',P,'q',zeros(length(P),1),{'t'});
        end

        function Psat = PsatT(obj,T)
            %PsatT Calculate saturation pressure from temperature.
            %   PSAT = PsatT(OBJ, T) calculates the saturation
            %   pressure corresponding to the specified temperature
            %   values using a vapor quality of zero.
            %
            %   Inputs:
            %       T - Temperature values in K.
            %
            %   Outputs:
            %       Psat - Saturation pressure in Pa.
            %
            %   See also: property, TsatP
            Psat = obj.property('t',T,'q',zeros(length(T),1),{'p'});
        end

        function s = saveobj(obj)
            %saveobj Prepare CoolPropWrapper for serialization.
            %   S = saveobj(OBJ) creates a serializable representation
            %   of the CoolPropWrapper instance.
            %
            %   Python-backed CoolProp handles are temporarily removed
            %   before invoking the built-in saveobj implementation
            %   because these handles cannot be serialized directly.
            %
            %   The original handles are restored after serialization.
            %
            %   Inputs:
            %       obj - CoolPropWrapper instance.
            %
            %   Outputs:
            %       s - Serialized representation of the object.
            %
            %   See also: loadobj
            
            % Save reference to CoolProp and CoolPropHandle
            temp_CoolProp = obj.CoolProp;
            temp_CoolPropHandle = obj.CoolPropHandle;

            % Remove reference to CoolProp and CoolPropHandle
            obj.CoolProp = -1;
            obj.CoolPropHandle = -1;
            
            % Store results of built-in saveobj function
            s = builtin('saveobj', obj);

            % Restore handles
            obj.CoolProp = temp_CoolProp;
            obj.CoolPropHandle = temp_CoolPropHandle;

        end
        
    end
    
    methods(Access=protected)
        function propVals = retrieveProps(obj, props)
            %retrieveProps Retrieve properties from the current state.
            %   PROPVALS = retrieveProps(OBJ, PROPS) retrieves the
            %   requested thermodynamic or transport properties from
            %   the current CoolProp AbstractState.
            %
            %   Inputs:
            %       props - Property identifiers, supplied as a
            %               character vector or cell array of
            %               character vectors.
            %
            %   Outputs:
            %       propVals - Column vector containing the requested
            %                  property values.
            %
            %   This method assumes the AbstractState has already
            %   been updated to the desired thermodynamic state.
            if ischar(props)
                props = {props};
            end
            propVals = zeros(numel(props),1);
            for k = 1:length(props)
                propName = lower(props{k});
                switch propName
                    case 'p', propVal = obj.CoolProp.p();
                    case 't', propVal = obj.CoolProp.T();
                    case 'h', propVal = obj.CoolProp.hmass();
                    case 's', propVal = obj.CoolProp.smass();
                    case 'k', propVal = obj.CoolProp.conductivity();
                    case 'mu', propVal = obj.CoolProp.viscosity();
                    case 'rho', propVal = obj.CoolProp.rhomass();
                    case 'pr', propVal = obj.CoolProp.Prandtl();
                    case 'cp', propVal = obj.CoolProp.cpmass();
                    case 'cv', propVal = obj.CoolProp.cvmass();
                    case 'gamma', propVal = obj.CoolProp.surface_tension();
                    case 'rhomolar', propVal = obj.CoolProp.rhomolar();
                    case 'q', propVal = obj.CoolProp.Q();
                    case 'ph', propVal = obj.CoolProp.phase();
                    otherwise, propVal = NaN;
                end
                propVals(k)= propVal;
            end
            
        end
        
        function propVals = property(obj,Alabel,A,Blabel,B, props)
            %property Calculate properties from two input variables.
            %   PROPVALS = property(OBJ, ALABEL, A, BLABEL, B, PROPS)
            %   calculates the requested properties for states defined
            %   by two thermodynamic input variables.
            %
            %   The method identifies the appropriate CoolProp input
            %   pair, updates the AbstractState, and retrieves the
            %   requested properties.
            %
            %   Input vectors are evaluated according to the selected
            %   output mode:
            %       'mat' - Evaluate all combinations of A and B.
            %       'vec' - Evaluate paired values, with scalar
            %               expansion when one input is scalar.
            %
            %   Inputs:
            %       Alabel - Identifier of the first input variable.
            %       A      - Values of the first input variable.
            %       Blabel - Identifier of the second input variable.
            %       B      - Values of the second input variable.
            %       props  - Cell array of requested property identifiers.
            %
            %   Outputs:
            %       propVals - Calculated property values.
            %
            %   See also: temperature, pressure, enthalpy, entropy, 
            %             density, conductivity, viscosity, cp, cv, prandtl, 
            %             surfaceTension, Phase, quality, TsatP, PsatT, 
            %             generateUpdatePair, retrieveProps
            
            % Determind input pair type
            [A, B, swapped] = obj.generateUpdatePair(Alabel, A, Blabel, B);
            
            n = numel(A);       % number of A points
            m = numel(B);       % number of B points
                        
            if obj.outputMode == 'mat'
                % setup propVals container
                propVals = zeros(n,m,numel(props));
                % For every pressure 
                for i = 1:n
                    % For every temperature
                    for j = 1:m
                        % Update AbstractState with AB
                        obj.CoolProp...
                            .update(obj.inputPairType, A(i), B(j));
                        % Retrieve properties.
                        propVals(i,j,:) = obj.retrieveProps(props);
                    end
                end

                % Matrix dimension consistency
                if swapped
                    propVals = permute(propVals, [2 1 3]);
                end
            else
                % lower dimension
                propVals = zeros(n,numel(props));
                % check if length(A)==length(B)
                if n~=m
                    if isscalar(A)
                        n = m;
                        A = A.*ones(n,1);
                    elseif isscalar(B)
                        m = n;
                        B = B.*ones(m,1);
                    else
                        error('Vector size mismatch');
                        return
                    end
                end
                 % For every pressure 
                for i = 1:n
                    % Update AbstractState with AB
                    obj.CoolProp...
                        .update(obj.inputPairType, A(i), B(i));
                    % Retrieve properties.
                    propVals(i,:) = obj.retrieveProps(props);
                end
            end
           
        end
        
        function getCoolPropParameters(obj)
            %getCoolPropParameters Retrieve available CoolProp parameters.
            %   getCoolPropParameters(OBJ) retrieves the parameter list
            %   from the CoolProp Python module and stores the parameter
            %   names in the params property.
            %
            %   See also: params
            obj.params = string(obj.CoolPropHandle.get('parameter_list'));
            obj.params = split(obj.params,',');
        end

        function input = scrubInput(obj,input)
            %scrubInput Normalize an input string.
            %   INPUT = scrubInput(OBJ, INPUT) normalizes a string by
            %   converting it to lowercase and removing leading and
            %   trailing whitespace.
            %
            %   Empty inputs are converted to an empty string.
            %
            %   Inputs:
            %       input - Input string or character vector.
            %
            %   Outputs:
            %       input - Normalized input string.
            if isempty(input)
                input = "";
            else
                input = strtrim(lower(input)); 
            end

        end

        function [A, B, swapped] = generateUpdatePair(obj, Alabel, A, Blabel, B)
            %generateUpdatePair Identify and configure a CoolProp input pair.
            %   [A, B, SWAPPED] = generateUpdatePair(OBJ, ALABEL, A,
            %   BLABEL, B) identifies the CoolProp input pair associated
            %   with the specified thermodynamic variables.
            %
            %   The method assigns the corresponding CoolProp input pair
            %   identifier to the inputPairType property and reorders
            %   the input values when necessary to match the required
            %   CoolProp variable ordering.
            %
            %   Inputs:
            %       Alabel - Identifier of the first input variable.
            %       A      - Values of the first input variable.
            %       Blabel - Identifier of the second input variable.
            %       B      - Values of the second input variable.
            %
            %   Outputs:
            %       A       - First input values, potentially reordered.
            %       B       - Second input values, potentially reordered.
            %       swapped - True if the input values were reordered.
            %
            %   See also: property

            swapped = false;
            
            % Clean labels
            Alabel = obj.scrubInput(Alabel);
            Blabel = obj.scrubInput(Blabel);
                        
            % Matching and swapping algorithm
            function isMatch = matchPair(Alabel, Blabel, Akey, Bkey)
                isMatch = (strcmp(Alabel, Akey) && strcmp(Blabel, Bkey)) || ...
                          (strcmp(Alabel, Bkey) && strcmp(Blabel, Akey));
                if isMatch && ~strcmp(Alabel, Akey)
                    C = B; B = A; A = C; swapped = true;
                end
            end
            
            % Find the correct input pair option
            if matchPair(Alabel,Blabel,'q','t')     % quality, temperature
                obj.inputPairType = obj.CoolPropHandle.QT_INPUTS;
            elseif matchPair(Alabel,Blabel,'p','q') % pressure, quality
                obj.inputPairType = obj.CoolPropHandle.PQ_INPUTS;
            elseif matchPair(Alabel,Blabel,'p','t') % pressure, temperature
                obj.inputPairType = obj.CoolPropHandle.PT_INPUTS;
            elseif matchPair(Alabel,Blabel,'d','t') % density, temperature
                obj.inputPairType = obj.CoolPropHandle.DmassT_INPUTS;
            elseif matchPair(Alabel,Blabel,'h','t') % enthalpy, temperature
                obj.inputPairType = obj.CoolPropHandle.HmassT_INPUTS;
            elseif matchPair(Alabel,Blabel,'s','t') % entropy, temperature
                obj.inputPairType = obj.CoolPropHandle.SmassT_INPUTS;
            elseif matchPair(Alabel,Blabel,'t','u') % termeprature, internal energy
                obj.inputPairType = obj.CoolPropHandle.TUmass_INPUTS;
            elseif matchPair(Alabel,Blabel,'d','h') % density, enthalpy
                obj.inputPairType = obj.CoolPropHandle.DmassHmass_INPUTS;
            elseif matchPair(Alabel,Blabel,'d','s') % density, entropy 
                obj.inputPairType = obj.CoolPropHandle.DmassSmass_INPUTS;
            elseif matchPair(Alabel,Blabel,'d','u') % density, internal energy
                obj.inputPairType = obj.CoolPropHandle.DmassUmass_INPUTS;
            elseif matchPair(Alabel,Blabel,'d','p') % density, pressure
                obj.inputPairType = obj.CoolPropHandle.DmassP_INPUTS;
            elseif matchPair(Alabel,Blabel,'d','q') % density, quality
                obj.inputPairType = obj.CoolPropHandle.DmassQ_INPUTS;
            elseif matchPair(Alabel,Blabel,'h','p') % enthalpy, pressure 
                obj.inputPairType = obj.CoolPropHandle.HmassP_INPUTS;
            elseif matchPair(Alabel,Blabel,'p','s') % pressure, entropy
                obj.inputPairType = obj.CoolPropHandle.PSmass_INPUTS;
            elseif matchPair(Alabel,Blabel,'p','u') % pressure, internal energy
                obj.inputPairType = obj.CoolPropHandle.PUmass_INPUTS;
            elseif matchPair(Alabel,Blabel,'h','s') % enthalpy, entropy
                obj.inputPairType = obj.CoolPropHandle.HmassSmass_INPUTS;
            elseif matchPair(Alabel,Blabel,'s','u') % entropy, internal energy 
                obj.inputPairType = obj.CoolPropHandle.SmassUmass_INPUTS;
            else % uh oh
                obj.inputPairType = obj.CoolPropHandle.INPUT_PAIR_INVALID;
            end
        end

        function phaseStr = phaseEnum2str(obj, phaseEnum)
            %phaseEnum2str Convert a CoolProp phase identifier to a string.
            %   PHASESTR = phaseEnum2str(OBJ, PHASEENUM) converts a
            %   CoolProp phase enumeration to its corresponding
            %   character vector.
            %
            %   Inputs:
            %       phaseEnum - CoolProp phase enumeration.
            %
            %   Outputs:
            %       phaseStr - Corresponding phase name.
            %
            %   See also: phaseStr2enum
            switch phaseEnum
                case 0, phaseStr = 'liquid';
                case 1, phaseStr = 'supercritical';
                case 2, phaseStr = 'supercritical_gas';
                case 3, phaseStr = 'supercritical_liquid';
                case 4, phaseStr = 'critical_point';
                case 5, phaseStr = 'gas';
                case 6, phaseStr = 'two_phase';
                case 7, phaseStr = 'unknown';
                case 8, phaseStr = 'not_imposed';
                otherwise, phaseStr = 'unset';
            end
        end

        function phaseEnum = phaseStr2enum(obj, phaseStr)
            %phaseStr2enum Convert a phase string to a CoolProp identifier.
            %   PHASEENUM = phaseStr2enum(OBJ, PHASESTR) converts a
            %   supported phase name to its corresponding CoolProp
            %   phase enumeration.
            %
            %   Inputs:
            %       phaseStr - Thermodynamic phase name.
            %
            %   Outputs:
            %       phaseEnum - Corresponding CoolProp phase enumeration.
            %
            %   See also: phaseEnum2str
            switch phaseStr
                case 'liquid'
                    phaseEnum = obj.CoolPropHandle.iphase_liquid;
                case 'supercritical'
                    phaseEnum = obj.CoolPropHandle.iphase_supercritical;
                case 'supercritical_gas'
                    phaseEnum = obj.CoolPropHandle.iphase_supercritical_gas;
                case 'supercritical_liquid'
                    phaseEnum = obj.CoolPropHandle.iphase_supercritical_liquid;
                case 'gas'
                    phaseEnum = obj.CoolPropHandle.iphase_gas;
                case 'twophase'
                    phaseEnum = obj.CoolPropHandle.iphase_twophase;
                case 'unknown'
                    phaseEnum = obj.CoolPropHandle.iphase_unknown;
                case 'not_imposed'
                    phaseEnum = obj.CoolPropHandle.iphase_not_imposed;
                otherwise
                    phaseEnum = NaN;
            end
        end
    end
    
    methods (Static)
        
        % Load serialized object. This is most often needed when
        % transferring between parpool workers and the host.
        function obj = loadobj(s)
            
            % TODO: there are other ways of loading obj that does not
            % guarantee s being obj already.
            obj = s;
            
            % Update the CoolProp handles
             obj.CoolPropHandle = py.importlib.import_module('CoolProp');
             obj.CoolProp = ...
                    obj.CoolPropHandle.AbstractState(obj.AbstractStateSrc, obj.fluid);
             obj.setFluid(s.fluid);    % Also sets the Abstract State handle
             obj.setPhase(s.as_phase);

        end

    end

    properties (Constant)
       EOS = struct('HEOS','HEOS',...
                    'TTSE_HEOS','TTSE&HEOS',...
                    'BICUBIC_HEOS','BICUBIC&HEOS');
    end
end

