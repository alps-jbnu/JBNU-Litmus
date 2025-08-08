import pickle
import json
import ast


if __name__ == '__main__':

    with open('./log.ksl', 'rb') as f:
        data = pickle.load(f)

    try:
        parse_data = {
            key: ast.literal_eval(value) if key.find('data') >= 0 else json.loads(data['obj'])
            for key, value in data.items()
        }

        print(json.dumps(parse_data, indent=4))
    except Exception as ex:

        try:
            data = str(data).replace('data_', '\n\ndata-')
            data = data.replace('\'obj', '\n\nobj')
            print(data)
        except Exception as ex2:
            print(ex, end='\n\n')
            print(ex2, end='\n\n')
            print(data)

