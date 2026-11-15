function verify_replay_inputs(inputSet, frozenPath)
% Assert every parsed effective input before solver construction.
frozen = jsondecode(fileread(frozenPath));
for group = ["model","options","geometry","bc"]
    expected = frozen.(group);
    actual = inputSet.(group);
    assert(numel(expected)==numel(actual),'MatchedReplay:InputCount','Input count differs: %s',group);
    for i=1:numel(expected)
        keys = fieldnames(expected(i));
        for j=1:numel(keys)
            key = keys{j};
            want = expected(i).(key); got = actual(i).(key);
            if strcmp(key,'CBTMULT')
                z = linspace(0,inputSet.geometry.LENGTH,inputSet.model.NNODES+1);
                value=got(z);
                pass=all(value==1,'all');
            elseif iscell(want)
                want = str2double(want);
                pass=isequaln(double(got(:)),double(want(:)));
            elseif isnumeric(want)||islogical(want)
                pass=isequaln(double(got(:)),double(want(:)));
                if strcmp(key,'WPOWER'), pass=pass&&isequal(size(got),size(want)); end
            else
                pass=strcmp(string(got),string(want));
            end
            assert(pass,'MatchedReplay:InputMismatch','Parsed input differs: %s(%d).%s',group,i,key);
        end
    end
end
fprintf('All frozen effective inputs match parsed MATLAB inputs.\n');
end
