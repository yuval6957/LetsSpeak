# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_core.ipynb.

# %% auto 0
__all__ = ['SpeechToText', 'TextToSpeech', 'get_embedding', 'ContextPool', 'CreateContext', 'get_response', 'chat']

# %% ../nbs/00_core.ipynb 3
import os
import pickle
from functools import partial

import numpy as np
from gtts import gTTS
import openai
import tiktoken
import whisper

from reinautils import Parameters



# %% ../nbs/00_core.ipynb 5
class SpeechToText:
    """
    _summary_: Speech to text using huggingface's wav2vec2 model.
    """
    
    def __init__(self):
        self.model = whisper.load_model("base")
    
    def __call__(self, file):
        return self.model.transcribe(file)['text']
    
class TextToSpeech:
    """
    _summary_: Text to speech using Google's TTS.
    """
    
    def __init__(self, lang='en'):
        self.model = gTTS
        self.lang = lang
    
    def __call__(self, text, file):
        tts = self.model(text=text, lang=self.lang, slow=False)
        tts.save(file)
        return file

# %% ../nbs/00_core.ipynb 9
def get_embedding(text, model="text-embedding-ada-002", return_num_tokens=False):
   text = text.replace("\n", " ")
   output = openai.Embedding.create(input = [text], model=model)
   return (output['data'][0]['embedding'], output["usage"]["total_tokens"]) if return_num_tokens else output['data'][0]['embedding']


# %% ../nbs/00_core.ipynb 10
class ContextPool:
    """
    A class used to store and retrieve text and their corresponding embeddings.

    ...

    Attributes
    ----------
    contexts : list
        A list storing the text data
    embeddings : np.array
        A numpy array storing the embeddings of the text
    file_name : str
        The file name to load data from and save data to

    Methods
    -------
    add(text: str)
        Adds the text to the contexts list and its corresponding embedding to the embeddings list.
    get(index: int)
        Returns the text and its corresponding embedding at the given index.
    __len__()
        Returns the length of the contexts list.
    pop(index: int)
        Removes the text and its corresponding embedding at the given index.
    __call__(text: str, n: int)
        Returns the 'n' most similar contexts to the given text based on their embeddings.
    save()
        Saves the contexts and embeddings to a file.
    load()
        Loads the contexts and embeddings from a file.
    """

    def __init__(self, file_name=None, model="text-embedding-ada-002"):
        """
        Constructs all the necessary attributes for the ContextPool object.

        Parameters:
            file_name (str): The file name to load data from and save data to.
        """
        self.contexts = []
        self.embeddings = np.array([])
        self.num_tokens = np.array([[]])
        self.file_name = file_name
        self.model = model
        self.get_embedding = partial(get_embedding, model=model)
        if self.file_name:
            self.load()

    def add(self, text):
        """
        Adds the text to the contexts list and its corresponding embedding to the embeddings list.
        """
        self.contexts.append(text)
        embedding, num_tokens = self.get_embedding(text, return_num_tokens=True)
        if self.embeddings.shape[0]:
            self.embeddings = np.append(self.embeddings, np.array(embedding)[None,:], axis=0)
        else:
            self.embeddings = np.array(embedding)[None,:]
        self.num_tokens = np.append(self.num_tokens, num_tokens)

    def get(self, index):
        """
        Returns the text and its corresponding embedding at the given index.

        Parameters:
            index (int): The index of the desired text and embedding.

        Returns:
            (str, np.array): The text and its corresponding embedding at the given index.
        """
        return self.contexts[index], self.embeddings[index], self.num_tokens[index]

    def __len__(self):
        """
        Returns the length of the contexts list.
        """
        return len(self.contexts)

    def pop(self, index):
        """
        Removes the text and its corresponding embedding at the given index.
        """
        self.contexts.pop(index)
        self.embeddings = np.delete(self.embeddings, index)
        self.num_tokens = np.delete(self.num_tokens, index)

    def __call__(self, text, n=1, threshold=0, too_close_threshold=0.9):
        """
        Returns the 'n' most similar contexts to the given text based on their embeddings.

        Parameters:
            text (str): The text to find the most similar contexts to.
            n (int): The number of most similar contexts to return.
            threshold (float): The minimum similarity required to return a context (between 0 and 1)

        Returns:
            (index or list of indexs): The 'n' most similar contexts to the given text.
        """
        if len(self.embeddings) == 0:
            return []
        similarity = np.dot(self.embeddings, get_embedding(text))
        
        if n==1:
            m = np.argmax(similarity)
            return [m] if similarity[m] > threshold else []
        else:
            m = np.argsort(similarity)[-2*n:]
            return [i for i in m if (similarity[i] > threshold) and (similarity[i] < too_close_threshold)][:n]

    def save(self):
        """
        Saves the contexts and embeddings to a file.
        """
        if self.file_name:
            with open(self.file_name, 'wb') as f:
                pickle.dump((self.contexts, self.embeddings, self.num_tokens), f)
        else:
            print("Error: No file name specified for saving.")

    def load(self):
        """
        Loads the contexts and embeddings from a file.
        """
        if self.file_name:
            try:
                with open(self.file_name, 'rb') as f:
                    self.contexts, self.embeddings, self.num_tokens = pickle.load(f)
            except FileNotFoundError:
                print(f"Error: File '{self.file_name}' not found. Starting with empty contexts and embeddings.")
        else:
            print("Error: No file name specified for loading. Is this your first time using this context?")


# %% ../nbs/00_core.ipynb 11
class CreateContext:
    """
    This class is responsible for assembling the full context text
    from the context pool and the request text.

    Attributes:
    context_pool (ContextPool): A ContextPool object that stores contexts and their embeddings.
    general_prompt (str): General prompt text that starts the assembled text.
    context_prompt (str): Context prompt text that introduces the contexts.
    request_prompt (str): Request prompt text that introduces the request.
    max_contexts_tokens (int): Maximum number of tokens that contexts can have in total.
    """
    
    def __init__(self, context_pool, general_prompt=None, context_prompt=None, request_prompt=None, last_n=2, max_contexts_tokens=512, threshold=0.5, too_close_threshold=0.95):
        """
        Initialize CreateContext with a context_pool and optional prompts.

        general_prompt, context_prompt, and request_prompt default to predefined texts if not specified.
        """
        self.context_pool = context_pool 
        self.general_prompt = "\nAnswer the request below using the following context" if general_prompt is None else general_prompt
        self.context_prompt = "\nContext:" if context_prompt is None else context_prompt
        self.request_prompt = "\nRequest:" if request_prompt is None else request_prompt
        self.max_contexts_tokens = max_contexts_tokens
        self.threshold = threshold
        self.too_close_threshold = too_close_threshold
        self.last_n = last_n
        
    def assemble(self, context, request):
        """
        Assemble the full context text from the given contexts and the request.

        Contexts that fit into max_contexts_tokens are joined with newlines,
        and the full context is formed with the prompts and the request.
        """
        full_context = []
        length = 0
        for m in context:
            if length + self.context_pool.num_tokens[m] < self.max_contexts_tokens:
                full_context.append(self.context_pool.contexts[m])
                length += self.context_pool.num_tokens[m]
        context_string = "\n".join(full_context)
        return f"{self.general_prompt}\n{self.context_prompt}\n{context_string}\n{self.request_prompt}\n{request}\n"     
    
    def related_contexts(self, text, n=5):
        """
        Get the contexts that are related to the given text from the context pool.

        The number of contexts and similarity thresholds can be adjusted.
        """
        last_context=list(range(len(self.context_pool)))[-self.last_n:]
        new_context = self.context_pool(text, n, self.threshold, self.too_close_threshold)
        last_context.extend([i for i in new_context if i not in last_context])
        return last_context[:n]
    
    def __call__(self, text, request, n=5):
        """
        Given the text and the request, assemble the full context with related contexts.

        This can be conveniently called as an instance object like a function.
        """
        context = self.related_contexts(text, n)
        return self.assemble(context, request)


# %% ../nbs/00_core.ipynb 12
def get_response(request, create_context, model= "gpt-3.5-turbo", n= 5, debug= False):
    """
    Get the response to the given request using the given context pool and model.
    """
    context = create_context(request, request)
    if debug:
        print(f"the content is:\n{context}\n#####\n")
    return openai.ChatCompletion.create(model=model, 
                                        messages =[{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": context}])["choices"][0]["message"]["content"]

# %% ../nbs/00_core.ipynb 13
def chat(create_context, context_pool, model= "gpt-3.5-turbo", n= 5, debug= False, auto_save= True):
    """
    Chat with the given context pool and model.
    """
    while True:
        try:
            request = input("Request: ")
        except EOFError as e:
            break
        if request == "quit":
            break
        response = get_response(request, create_context, model, n , debug)
        context_pool.add(f"user:{request}\nassistant:{response}")
        print(f"Request: {request}")
        print(f"Response: {response}")
        if auto_save:
            context_pool.save()


